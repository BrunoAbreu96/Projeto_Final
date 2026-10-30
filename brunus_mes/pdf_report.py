"""Geração do PDF a partir do mesmo modelo usado pela interface."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .reporting import DEMO_DOWNTIME_PER_MINUTE, DEMO_MARGIN_OK, DEMO_SCRAP_COST, ShiftReport


def generate_shift_pdf(report: ShiftReport) -> bytes:
    """Produz um PDF auditável, sem voltar a consultar a base de dados."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title="BRUNUS MES - Relatório de turno",
        author="BRUNUS MES", leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 9.5
    styles["BodyText"].leading = 11.5
    styles["BodyText"].spaceBefore = 3
    styles["BodyText"].spaceAfter = 3
    styles["Title"].fontSize = 19
    styles["Title"].leading = 22
    styles["Title"].spaceAfter = 9
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 14
    styles["Heading2"].spaceBefore = 6
    styles["Heading2"].spaceAfter = 6
    story = []

    def paragraph(value, style="BodyText"):
        story.append(Paragraph(value, styles[style]))

    def table(rows):
        wrapped = [[Paragraph(escape(str(value)), styles["BodyText"]) for value in row] for row in rows]
        result = Table(wrapped, colWidths=[315, 200], repeatRows=1, hAlign="LEFT")
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edf3")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d0d8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(result)
        story.append(Spacer(1, 6))

    paragraph("BRUNUS MES - Relatório de turno", "Title")
    paragraph(f"<b>Data de início:</b> {report.day.strftime('%d/%m/%Y')} - {escape(report.shift_label)}")
    paragraph(f"<b>Intervalo:</b> {report.start:%d/%m/%Y %H:%M} (incluído) a {report.end:%d/%m/%Y %H:%M} (excluído).")
    paragraph(f"<b>Instante da consulta:</b> {report.snapshot:%d/%m/%Y %H:%M:%S}. Horas locais, sem fuso horário.")
    paragraph(f"<b>Dados e paragens limitados a:</b> {report.effective_end:%d/%m/%Y %H:%M:%S}.")
    story.append(Spacer(1, 12))
    if not report.has_data:
        paragraph("Sem dados de produção nem avarias para o período selecionado.", "Heading2")
    table([
        ("Produção e qualidade", "Valor"),
        ("Peças processadas (saídas finais de linha)", report.total_pieces),
        ("Peças conformes (OK)", report.ok_pieces),
        ("Peças rejeitadas", report.rejected_pieces),
        ("Qualidade FTT (OK / total × 100)", f"{report.quality_percent:.2f}%" if report.quality_percent is not None else "Sem produção"),
    ])
    paragraph("O FTT mede apenas qualidade. Não constitui um cálculo completo de OEE.")
    story.append(Spacer(1, 8))
    table([
        ("Avarias e paragens", "Valor"),
        ("Ocorrências iniciadas no turno", report.occurrences),
        ("Avarias com paragem coincidente com o turno", report.overlapping_breakdowns),
        ("Dessas avarias, ainda ativas na consulta", report.active_breakdowns),
        ("Reparações concluídas da coorte de início no turno", report.completed_repairs),
        ("MTTR dessa coorte (duração completa)", f"{report.mttr_seconds:.2f} s" if report.mttr_seconds is not None else "Sem reparações concluídas"),
        ("Indisponibilidade acumulada das linhas", f"{report.downtime_line_seconds:.2f} segundos-linha"),
        *[(f"Paragem de {line}", f"{seconds:.2f} s") for line, seconds in report.downtime_by_line.items()],
    ])
    paragraph("As ocorrências contam pelo início da avaria. A paragem inclui avarias anteriores que intersetam o turno, recorta os intervalos ao período e une sobreposições da mesma linha. Linhas diferentes somam segundos-linha, não tempo de paragem da célula.")
    paragraph("As avarias abertas contam até ao instante da consulta ou fim do turno, o que ocorrer primeiro. O MTTR inclui apenas avarias iniciadas no turno e concluídas até à consulta; usa toda a duração da reparação, mesmo fora do turno.")
    story.append(Spacer(1, 8))
    financial_start = len(story)
    paragraph("Estimativas financeiras de demonstração", "Heading2")
    table([
        ("Estimativa (parâmetros de demonstração)", "Valor"),
        ("Margem teórica das peças OK", f"EUR {report.estimated_margin:,.2f}"),
        ("Custo estimado de rejeições", f"EUR {report.estimated_scrap_cost:,.2f}"),
        ("Custo estimado da paragem das linhas", f"EUR {report.estimated_downtime_cost:,.2f}"),
        ("Resultado estimado", f"EUR {report.estimated_result:,.2f}"),
    ])
    paragraph(f"Parâmetros de demonstração: EUR {DEMO_MARGIN_OK:.2f} de margem por peça OK; EUR {DEMO_SCRAP_COST:.2f} por peça rejeitada; EUR {DEMO_DOWNTIME_PER_MINUTE:.2f} por minuto-linha de paragem.")
    paragraph("Resultado estimado = peças OK × margem - rejeições × custo unitário - segundos-linha / 60 × custo por minuto-linha. Estes valores simulados não representam lucro efetivamente apurado.")
    # Keep the financial result, its parameters and its interpretation together.
    financial_section = story[financial_start:]
    del story[financial_start:]
    story.append(KeepTogether(financial_section))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(36, 22, "BRUNUS MES - Dados e parâmetros de demonstração")
        canvas.drawRightString(A4[0] - 36, 22, f"Página {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
