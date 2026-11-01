#!/usr/bin/env python3
"""Create the Chinese engineering report for the CFD submission package."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "CFD_output" / "results" / "coaxial_hover_310rpm"
OUTPUT = ROOT / "output" / "pdf" / "Coaxial_Rotor_CFD_Report_zh.pdf"

NAVY = colors.HexColor("#15324A")
BLUE = colors.HexColor("#2D6A8A")
TEAL = colors.HexColor("#2A9D8F")
ORANGE = colors.HexColor("#E76F51")
LIGHT = colors.HexColor("#EEF4F7")
MID = colors.HexColor("#6B7C86")


def fit_image(path: Path, max_width: float, max_height: float) -> Image:
    with PILImage.open(path) as image:
        width, height = image.size
    scale = min(max_width / width, max_height / height)
    return Image(str(path), width=width * scale, height=height * scale)


def footer_and_header(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#D8E1E6"))
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, height - 14 * mm, width - 18 * mm, height - 14 * mm)
    canvas.setFont("SimHei", 7.5)
    canvas.setFillColor(MID)
    canvas.drawString(18 * mm, height - 11.5 * mm, "COAXIAL ROTOR CFD  |  TECHNICAL REPORT")
    canvas.drawRightString(width - 18 * mm, height - 11.5 * mm, "2026-11-02")
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.drawString(18 * mm, 9.5 * mm, "Engineering baseline - not for certification")
    canvas.drawRightString(width - 18 * mm, 9.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def section_title(text: str) -> Paragraph:
    return Paragraph(text, styles["H1"])


def body(text: str) -> Paragraph:
    return Paragraph(text, styles["Body"])


def bullet(text: str) -> Paragraph:
    return Paragraph(text, styles["Bullet"])


def metric_table(rows: list[list[str]], widths: list[float] | None = None) -> Table:
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "SimHei"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CAD5DA")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


pdfmetrics.registerFont(TTFont("SimHei", r"C:\Windows\Fonts\simhei.ttf"))

sample = getSampleStyleSheet()
styles = {
    "CoverTitle": ParagraphStyle(
        "CoverTitle",
        parent=sample["Title"],
        fontName="SimHei",
        fontSize=26,
        leading=34,
        textColor=NAVY,
        alignment=TA_LEFT,
        spaceAfter=8,
    ),
    "CoverSub": ParagraphStyle(
        "CoverSub",
        parent=sample["Normal"],
        fontName="SimHei",
        fontSize=11,
        leading=17,
        textColor=MID,
        spaceAfter=6,
    ),
    "H1": ParagraphStyle(
        "H1",
        parent=sample["Heading1"],
        fontName="SimHei",
        fontSize=17,
        leading=22,
        textColor=NAVY,
        spaceBefore=8,
        spaceAfter=9,
    ),
    "H2": ParagraphStyle(
        "H2",
        parent=sample["Heading2"],
        fontName="SimHei",
        fontSize=11.5,
        leading=16,
        textColor=BLUE,
        spaceBefore=8,
        spaceAfter=5,
    ),
    "Body": ParagraphStyle(
        "Body",
        parent=sample["BodyText"],
        fontName="SimHei",
        fontSize=9.2,
        leading=14.5,
        textColor=colors.HexColor("#23343D"),
        spaceAfter=7,
    ),
    "Bullet": ParagraphStyle(
        "Bullet",
        parent=sample["BodyText"],
        fontName="SimHei",
        fontSize=9.2,
        leading=14.5,
        leftIndent=14,
        firstLineIndent=-9,
        textColor=colors.HexColor("#23343D"),
        spaceAfter=4,
    ),
    "Caption": ParagraphStyle(
        "Caption",
        parent=sample["BodyText"],
        fontName="SimHei",
        fontSize=8,
        leading=11,
        textColor=MID,
        alignment=TA_CENTER,
        spaceAfter=7,
    ),
    "Small": ParagraphStyle(
        "Small",
        parent=sample["BodyText"],
        fontName="SimHei",
        fontSize=8,
        leading=12,
        textColor=MID,
    ),
}


def build() -> None:
    summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    force = json.loads((RESULTS / "total_force.json").read_text(encoding="utf-8"))
    lower = force["lower"]
    upper = force["upper"]
    total = force["total"]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=19 * mm,
        title="共轴双旋翼流体力学仿真报告",
        author="Huiteng Zhuang",
        subject="OpenFOAM steady MRF CFD engineering baseline",
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="main",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates(
        [
            PageTemplate(
                id="cover",
                frames=[frame],
                onPage=lambda canvas, doc: None,
            ),
            PageTemplate(id="content", frames=[frame], onPage=footer_and_header),
        ]
    )

    story = []
    story.append(Paragraph("共轴双旋翼流体力学仿真", styles["CoverTitle"]))
    story.append(
        Paragraph(
            "基于实际 CAD 几何的 OpenFOAM 稳态 MRF 分析",
            styles["CoverSub"],
        )
    )
    story.append(
        Paragraph(
            "Technical report  |  310 rpm hover baseline  |  2 November 2026",
            styles["CoverSub"],
        )
    )
    story.append(Spacer(1, 7 * mm))
    story.append(
        fit_image(
            ROOT / "docs" / "images" / "rotor-surface-pressure.png",
            174 * mm,
            108 * mm,
        )
    )
    story.append(
        Paragraph(
            "修正上层桨距方向后的共轴转子表面压力分布",
            styles["Caption"],
        )
    )
    cover_metrics = [
        ["总升力", "257.07 N"],
        ["参考重量", "249.97 N"],
        ["净反扭矩", "0.84 N·m"],
        ["估算轴功率", "2.45 kW"],
    ]
    table = metric_table(cover_metrics, [65 * mm, 102 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CAD5DA")),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 5 * mm))
    story.append(
        Paragraph(
            "工程筛选级结果。用于设计方向判断和方案对比，不作为适航、强度或最终性能认证依据。",
            styles["Small"],
        )
    )
    story.append(NextPageTemplate("content"))
    story.append(PageBreak())

    story.append(section_title("1. 交付摘要"))
    story.append(
        body(
            "本项目读取了双层三桨叶共轴装配，使用实际叶片曲面建立全三维流体域，"
            "以 OpenFOAM v1912 的 simpleFoam 求解稳态多重参考系（MRF）流场，"
            "并对上下转子的压力和壁面剪切进行积分。"
        )
    )
    summary_rows = [
        ["项目", "结果"],
        ["下层 / 上层转速", "+310 / -310 rpm"],
        ["下层升力", f"{lower['total_force_n'][1]:.2f} N"],
        ["上层升力", f"{upper['total_force_n'][1]:.2f} N"],
        ["总升力", f"{total['force_n'][1]:.2f} N"],
        ["参考重量", "249.97 N"],
        ["升重比", "1.028"],
        ["下层 / 上层轴向反扭矩", f"{lower['total_torque_nm'][1]:.2f} / {upper['total_torque_nm'][1]:.2f} N·m"],
        ["净轴向反扭矩", f"{total['torque_nm'][1]:.2f} N·m"],
        ["估算轴功率", "2.45 kW"],
        ["估算悬停效率", "0.436"],
    ]
    story.append(metric_table(summary_rows, [94 * mm, 73 * mm]))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("关键发现", styles["H2"]))
    story.append(
        bullet(
            "原始装配在两层反向旋转时，两个转子分别产生约 0.8-0.9 kN 的相反轴向力，净升力接近零。"
        )
    )
    story.append(
        bullet(
            "该现象不是转速不足造成，而是上层桨叶桨距方向与预期反向旋转不匹配。"
        )
    )
    story.append(
        bullet(
            "仅镜像上层桨叶桨距方向后，两转子形成升力同向、反扭矩相互抵消的共轴配置。"
        )
    )
    story.append(
        bullet(
            "按升力随转速平方近似缩放，250 N 配平转速约 306 rpm；本次采用 310 rpm 作为保守悬停点。"
        )
    )
    story.append(PageBreak())

    story.append(section_title("2. 几何与方法"))
    story.append(
        fit_image(
            ROOT / "docs" / "images" / "assembly-preview.png",
            102 * mm,
            76 * mm,
        )
    )
    story.append(
        Paragraph("原始 SolidWorks 装配预览", styles["Caption"])
    )
    story.append(
        body(
            "装配数据确认每层 3 片桨叶、桨尖半径 1.40 m、桨根半径 0.27 m、"
            "两层转子间距 0.56 m。桨叶三角网格为闭合实体，体积为 "
            "0.00292383 m3，SolidWorks 记录值为 0.00294411 m3，差约 0.69%。"
        )
    )
    story.append(
        body(
            "原生桨毂存在少量自动转换器无法完整重建的圆环裁剪面，因此 CFD "
            "使用与提取外轮廓一致的三臂桨毂简化体。上层修正只涉及桨叶桨距方向，"
            "没有改变桨叶尺寸或装配间距。"
        )
    )
    method_rows = [
        ["阶段", "处理方式"],
        ["原生几何", "SolidWorks 装配、质量属性与组件变换矩阵"],
        ["叶片转换", "裁剪 UV 面采样、受约束三角化、网格修复"],
        ["计算域", "11 m × 9 m × 11 m 全 360° 流体域"],
        ["旋转区域", "半径 1.55 m 的上下两个圆柱 MRF 区域"],
        ["数值模型", "simpleFoam + steady MRF + kOmegaSST"],
        ["流体", "20°C 空气，rho=1.204 kg/m3，nu=1.516e-5 m2/s"],
    ]
    story.append(metric_table(method_rows, [40 * mm, 127 * mm]))
    story.append(PageBreak())

    story.append(section_title("3. 网格与数值稳定性"))
    mesh_rows = [
        ["指标", "结果"],
        ["单元数", "461,545"],
        ["点 / 面数", "498,053 / 1,419,861"],
        ["最大非正交角", "62.22°"],
        ["最大偏斜度", "4.20"],
        ["高偏斜面", "1"],
        ["凹多面体单元", "5,260"],
        ["Uy 初始残差", "4.36e-5"],
        ["压力初始残差", "9.50e-6"],
        ["局部连续性误差", "1.97e-6"],
        ["全局连续性误差", "7.56e-7"],
    ]
    story.append(metric_table(mesh_rows, [85 * mm, 82 * mm]))
    story.append(Spacer(1, 7 * mm))
    story.append(
        body(
            "总升力在 200 次和 300 次迭代时分别为 257.12 N 和 257.07 N，"
            "变化小于 0.03%，说明主要气动载荷已达到稳定。"
        )
    )
    story.append(
        fit_image(
            ROOT / "docs" / "images" / "centerline.png",
            170 * mm,
            92 * mm,
        )
    )
    story.append(
        Paragraph("转子轴附近的轴向速度与压力分布", styles["Caption"])
    )
    story.append(
        body(
            "网格在叶片附近局部加密至约 0.017 m。checkMesh 的负体积、边界开放度、"
            "面金字塔和单元行列式检查通过，但仍报告 1 个高偏斜面及 5,260 个凹多面体单元。"
            "因此本结果适合方案筛选，不应用于最终认证。"
        )
    )
    story.append(PageBreak())

    story.append(section_title("4. 流场与性能结果"))
    story.append(
        fit_image(
            ROOT / "docs" / "images" / "performance-summary.png",
            170 * mm,
            68 * mm,
        )
    )
    story.append(
        Paragraph("修正共轴配置在 310 rpm 下的升力与反扭矩", styles["Caption"])
    )
    story.append(
        fit_image(
            ROOT / "docs" / "images" / "velocity-pressure-slice.png",
            174 * mm,
            82 * mm,
        )
    )
    story.append(
        Paragraph("z=0 纵向切片：速度幅值（左）与静压（右）", styles["Caption"])
    )
    story.append(
        body(
            "上下两层的轴向反扭矩分别约为 -37.35 N·m 和 +38.19 N·m，"
            "在机架上的净反扭矩约 0.84 N·m。轴功率按两层扭矩幅值之和估算为 "
            "2.45 kW；采用单层桨盘面积进行理想动量理论估计，悬停效率约 0.436。"
        )
    )
    story.append(PageBreak())

    story.append(section_title("5. 使用边界与建议"))
    story.append(Paragraph("必须保留的说明", styles["H2"]))
    story.append(bullet("稳态 MRF 冻结叶片周向位置，不解析叶片通过频率及瞬态尾迹。"))
    story.append(bullet("无边界层棱柱层，壁面剪切由首层速度梯度和壁面函数黏度估算。"))
    story.append(bullet("桨毂为简化几何；上层桨叶桨距为设计修正。"))
    story.append(bullet("310 rpm 是按 25.49 kg 装配重量选取的工程悬停点，不是实测工况。"))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("建议的下一阶段", styles["H2"]))
    story.append(bullet("在 SolidWorks 中正式建立上层镜像桨叶，而不是依赖后处理镜像。"))
    story.append(bullet("恢复完整桨毂几何，增加叶片边界层并做网格无关性验证。"))
    story.append(bullet("采用瞬态滑移网格评估叶片通过频率、噪声与动态载荷。"))
    story.append(bullet("提供真实电机转速、总重和飞行状态后，重新校准悬停点。"))
    story.append(Spacer(1, 7 * mm))
    story.append(Paragraph("交付文件", styles["H2"]))
    deliverables = [
        ["文件", "内容"],
        ["本 PDF", "技术摘要、方法、结果和限制"],
        ["total_force.json", "上下转子压力、壁面剪切与力矩"],
        ["summary.json", "算例参数、残差和性能指标"],
        ["VTK/", "最终流场与转子表面数据"],
        ["case_corrected_310_complete.tar.gz", "完整 OpenFOAM 可复算算例"],
        ["source_models/", "提交方提供的原始 CAD 文件"],
    ]
    story.append(metric_table(deliverables, [77 * mm, 90 * mm]))
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "报告作者：Huiteng Zhuang  |  计算日期：2026-11-02  |  "
            "OpenFOAM v1912",
            styles["Small"],
        )
    )

    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    build()
