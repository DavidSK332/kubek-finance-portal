"""PDF and plain-text reports share the same immutable financial snapshot."""
import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from schemas import DEBT_TYPES, GOALS

FONT_PATH = Path(__file__).parent / "assets" / "fonts"
NAVY = colors.HexColor("#142b37")
TEAL = colors.HexColor("#087f75")
MUTED = colors.HexColor("#526773")


def money(value):
    if value is None:
        return "neurčené"
    return f"{float(value):,.2f}".replace(",", " ").replace(".", ",") + " EUR"


def number(value, suffix=""):
    return "neurčené" if value is None else f"{float(value):.2f}".replace(".", ",") + suffix


def build_report(snapshot, internal=False):
    if "Portal" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Portal", str(FONT_PATH / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("PortalBold", str(FONT_PATH / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("Portal", normal="Portal", bold="PortalBold", italic="Portal", boldItalic="PortalBold")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="PortalBody", fontName="Portal", fontSize=9, leading=14,
                              textColor=NAVY, spaceAfter=7, splitLongWords=True))
    styles.add(ParagraphStyle(name="PortalTitle", parent=styles["PortalBody"], fontName="PortalBold", fontSize=23, leading=29, spaceAfter=12))
    styles.add(ParagraphStyle(name="PortalH2", parent=styles["PortalBody"], fontName="PortalBold", fontSize=12, leading=18, spaceBefore=15, spaceAfter=8, keepWithNext=True))
    styles.add(ParagraphStyle(name="PortalSmall", parent=styles["PortalBody"], fontSize=8, leading=12, textColor=MUTED))
    def p(text, style="PortalBody"):
        safe = escape(str(text)).replace("\n", "<br/>")
        return Paragraph(safe, styles[style])
    def table(rows, widths, header=False):
        cells = [[p(value, "PortalSmall" if header and i == 0 else "PortalBody") for value in row] for i, row in enumerate(rows)]
        result = LongTable(cells, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe7ea")),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f1f7f6"), colors.white])]
        if header:
            commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e1efed")))
        result.setStyle(TableStyle(commands))
        return result
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=(210 * mm, 297 * mm), rightMargin=20 * mm,
                            leftMargin=20 * mm, topMargin=29 * mm, bottomMargin=22 * mm,
                            title="Finančný prehľad", author=snapshot["organization"])
    def page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, 280 * mm, 210 * mm, 17 * mm, fill=1, stroke=0)
        canvas.setFont("PortalBold", 10)
        canvas.setFillColor(colors.white)
        canvas.drawString(20 * mm, 286 * mm, snapshot["organization"][:60])
        canvas.setFillColor(MUTED)
        canvas.setFont("Portal", 8)
        canvas.drawString(20 * mm, 12 * mm, "Interný podklad pre agenta" if internal else "Pracovný návrh finančného riešenia")
        canvas.drawRightString(190 * mm, 12 * mm, f"Strana {document.page}")
        canvas.restoreState()
    data, profile = snapshot["data"], snapshot["metrics"]
    story = [p("Finančný profil klienta" if internal else "Váš finančný prehľad", "PortalTitle"),
             p(f"{data['first_name']} {data['last_name']} | {snapshot['created_label']}", "PortalSmall"),
             p(f"Pripravil: {snapshot['agent_name']} | {snapshot['agent_email']}", "PortalSmall"),
             p("01 / Súčasná situácia", "PortalH2")]
    story.append(table([
        ["Čistý mesačný príjem domácnosti", money(profile["income"])],
        ["Bežné výdavky bez úverových splátok", money(profile["expenses"])],
        ["Mesačné úverové splátky", money(profile["payments"])],
        ["Disponibilný mesačný zostatok", money(profile["disposable"])],
        ["Celkový čerpaný dlh", money(profile["debt"])],
        ["DTI (dlh / ročný čistý príjem)", number(profile["dti"], " x")],
        ["Pomer splátok k príjmu (bez ŽM a stresu)", number(profile["debt_service_ratio"], " %")],
        ["Dostupná finančná rezerva", money(data["savings"])],
    ], [110 * mm, 60 * mm]))
    if data["debts"]:
        story += [p("Prehľad záväzkov", "PortalH2"), table(
            [["Záväzok / inštitúcia", "Zostatok", "Splátka", "Úrok p. a."]] +
            [[DEBT_TYPES[d["kind"]] + (" / " + d["lender"] if d["lender"] else ""),
              money(d["balance"]), money(d["payment"]), number(d["rate"], " %")] for d in data["debts"]],
            [66 * mm, 37 * mm, 36 * mm, 31 * mm], True)]
    proposal = snapshot.get("proposal")
    if proposal:
        comparison = snapshot["comparison"]
        if not internal:
            story.append(PageBreak())
        story += [p("02 / Navrhované riešenie", "PortalH2"), p(proposal["client_summary"]),
                  p(f"Vybraná inštitúcia / riešenie: {proposal['lender']}")]
        if proposal["kind"] in ("mortgage", "refinance"):
            story += [p(f"Úver {money(proposal['principal'])}, sadzba {number(proposal['annual_rate'], ' % p. a.')}, "
                        f"splatnosť {proposal['years']} rokov. Modelová anuitná splátka {money(comparison['loan_payment'])}.")]
        story.append(table([
            ["Ukazovateľ", "Teraz", "Po návrhu"],
            ["Čerpaný dlh", money(profile["debt"]), money(comparison["debt_after"])],
            ["Splátky dlhov / mesiac", money(profile["payments"]), money(comparison["payments_after"])],
            ["Nové pravidelné náklady / mesiac", money(0), money(comparison["monthly_costs"])],
            ["Disponibilný zostatok / mesiac", money(profile["disposable"]), money(comparison["disposable_after"])],
        ], [76 * mm, 47 * mm, 47 * mm], True))
        story += [Spacer(1, 4 * mm), p(f"Zmena mesačného zostatku: {money(comparison['monthly_change'])}. "
                    f"Za 12 mesiacov pri rovnakých podmienkach: {money(comparison['annual_change'])}. "
                    f"Jednorazové náklady: {money(comparison['upfront_fees'])}."),
                  p("Kladná zmena znamená viac voľných peňazí, záporná zvýšenie mesačných výdavkov. "
                    "Pokles splátky pri dlhšej splatnosti nepreukazuje úsporu na celkových nákladoch.", "PortalSmall")]
        if comparison["loan_total_estimate"] is not None:
            story.append(p(f"Modelová celková platba nového úveru vrátane zadaných poplatkov a nových "
                           f"pravidelných nákladov: {money(comparison['loan_total_estimate'])}. "
                           "Predpokladá nemennú sadzbu a náklady počas celej splatnosti; nejde o RPMN.", "PortalSmall"))
        if comparison["dsti_estimate"] is not None:
            story.append(p(f"Orientačný DSTI zo splátok a ŽM zadaných agentom: "
                           f"{number(comparison['dsti_estimate'], ' %')}. Správnosť vstupov overuje agent.", "PortalSmall"))
        story.append(p("03 / Podklady a ďalší postup", "PortalH2"))
        for index, item in enumerate(proposal["documents"], 1):
            story.append(p(f"{index}. {item}"))
    if internal:
        story += [p("Kontaktné a vstupné údaje", "PortalH2"),
                  p(f"E-mail: {data['email']} | Telefón: {data['phone']}"),
                  p(f"Vek: {data['age']} | Dospelí v domácnosti: {data['adults']} | Deti: {data['children']}"),
                  p("Ciele: " + ", ".join(GOALS[g] for g in data["goals"])),
                  p(f"Požadovaný úver: {money(data['requested_loan'])} / {data['requested_years']} rokov."),
                  p("Poznámky klienta: " + (data["notes"] or "Bez poznámok.")),
                  p("Analytický komentár - pred použitím skontrolovať", "PortalH2")]
        analysis = snapshot.get("analysis")
        if analysis:
            story.append(p(analysis["summary"]))
            for key, label in (("strengths", "Silné stránky"), ("risks", "Riziká"),
                               ("next_steps", "Ďalšie kroky"), ("missing_data", "Chýbajúce údaje")):
                story.append(p(label, "PortalH2"))
                story.extend(p("- " + line) for line in analysis[key])
        else:
            story.append(p("Analýza zatiaľ nebola dokončená."))
    story += [p("Rozsah výpočtu", "PortalH2"),
              p("Údaje sú deklarované klientom. Výpočty nezaručujú schválenie úveru ani výhodnosť produktu. "
                "Bankové posúdenie zohľadňuje uznaný príjem, registre, životné minimum, stresované splátky, "
                "úverové limity, zabezpečenie a vlastnú metodiku. Predpokladaná splátka nezahŕňa poplatky, "
                "ak neboli uvedené osobitne. Návrh platí iba za uvedených predpokladov.", "PortalSmall")]
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()


def report_text(snapshot, internal=False):
    data, metrics = snapshot["data"], snapshot["metrics"]
    lines = [f"Dobrý deň{',' if internal else ' ' + data['first_name'] + ','}", "",
             "pripravili sme finančný prehľad podľa poskytnutých údajov.", "",
             f"Klient: {data['first_name']} {data['last_name']}",
             f"Čistý príjem domácnosti: {money(metrics['income'])} / mesiac",
             f"Bežné výdavky: {money(metrics['expenses'])} / mesiac",
             f"Úverové splátky: {money(metrics['payments'])} / mesiac",
             f"Disponibilný zostatok: {money(metrics['disposable'])} / mesiac",
             f"Čerpaný dlh: {money(metrics['debt'])}",
             f"DTI: {number(metrics['dti'], ' x')}",
             f"Pomer splátok k príjmu bez ŽM a stresu: {number(metrics['debt_service_ratio'], ' %')}"]
    proposal = snapshot.get("proposal")
    if proposal:
        comparison = snapshot["comparison"]
        lines += ["", "NAVRHOVANÉ RIEŠENIE", proposal["client_summary"],
                  f"Inštitúcia / riešenie: {proposal['lender']}",
                  f"Modelová splátka nového úveru: {money(comparison['loan_payment'])}",
                  f"Splátky po zmene: {money(comparison['payments_after'])}",
                  f"Nové pravidelné náklady: {money(comparison['monthly_costs'])}",
                  f"Zostatok po zmene: {money(comparison['disposable_after'])}",
                  f"Zmena voľných peňazí mesačne: {money(comparison['monthly_change'])}",
                  f"Jednorazové náklady: {money(comparison['upfront_fees'])}",
                  "Nižšia splátka sama osebe nepreukazuje nižšie celkové náklady.",
                  "", "POTREBNÉ PODKLADY"]
        lines += [f"- {item}" for item in proposal["documents"]]
    if internal:
        lines += ["", f"Kontakt: {data['email']} | {data['phone']}",
                  f"Vek: {data['age']}, dospelí: {data['adults']}, deti: {data['children']}",
                  f"Príjem zo zamestnania: {money(data['income_employment'])}",
                  f"Príjem zo živnosti: {money(data['income_business'])}",
                  f"Osobný príjem zo s.r.o.: {money(data['income_company'])}",
                  f"Iné príjmy: {money(data['income_other'])}",
                  "Ciele: " + ", ".join(GOALS[g] for g in data["goals"]),
                  f"Požadovaný úver: {money(data['requested_loan'])} / {data['requested_years']} rokov",
                  f"Plánované investovanie: {money(data['monthly_investment'])} / mesiac",
                  "Poznámky: " + (data["notes"] or "Bez poznámok.")]
        for debt in data["debts"]:
            lines.append(f"{DEBT_TYPES[debt['kind']]} / {debt['lender']}: zostatok {money(debt['balance'])}, "
                         f"splátka {money(debt['payment'])}, sadzba {number(debt['rate'], ' %')}, limit {money(debt['limit'])}")
        analysis = snapshot.get("analysis")
        if analysis:
            lines += ["", "ANALYTICKÝ KOMENTÁR - SKONTROLOVAŤ", analysis["summary"]]
            for key, label in (("strengths", "Silné stránky"), ("risks", "Riziká"),
                               ("next_steps", "Ďalšie kroky"), ("missing_data", "Chýbajúce údaje")):
                lines += [label] + ["- " + line for line in analysis[key]]
    lines += ["", "Podrobný report je v PDF prílohe. Ide o pracovný návrh, nie schválenie bankou.",
              "", snapshot["agent_name"], snapshot["organization"], snapshot["agent_email"]]
    return "\n".join(lines)
