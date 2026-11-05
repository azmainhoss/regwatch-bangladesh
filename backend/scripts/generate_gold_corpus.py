import os
from pathlib import Path
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def generate_all_gold_fixtures():
    corpus_dir = Path("backend/app/tests/fixtures/corpus")
    corpus_dir.mkdir(parents=True, exist_ok=True)

    # 1. English Native Digital with Table and Clauses
    # (bb_brpd_2024_15.pdf already exists from Phase 1, ensure it's up to date)
    pdf_en = corpus_dir / "gold_en_digital_master_policy.pdf"
    c_en = canvas.Canvas(str(pdf_en), pagesize=letter)
    c_en.setFont("Helvetica-Bold", 14)
    c_en.drawString(200, 750, "BANGLADESH BANK")
    c_en.setFont("Helvetica", 11)
    c_en.drawString(180, 735, "Head Office, Motijheel, Dhaka-1000")
    c_en.drawString(160, 720, "Banking Regulation and Policy Department (BRPD)")
    c_en.drawString(50, 680, "BRPD Circular No. 15")
    c_en.drawString(450, 680, "Date: 27 November 2024")
    c_en.drawString(50, 660, "Managing Director / Chief Executive Officer")
    c_en.drawString(50, 645, "All Scheduled Commercial Banks operating in Bangladesh")
    c_en.setFont("Helvetica-Bold", 12)
    c_en.drawString(50, 615, "Subject: Master Policy on Loan Classification and Provisioning Alignment with IFRS 9")
    c_en.setFont("Helvetica", 10)
    lines_p1 = [
        "Dear Sir,",
        "Please refer to BRPD Circular No. 14 dated 23 September 2012 and subsequent instructions issued on",
        "loan classification and provisioning standards for scheduled commercial banks.",
        "",
        "1. Mandatory Staging Framework:",
        "All scheduled commercial banks must classify their credit facilities into three distinct stages:",
        "  1.1 Stage 1 (Performing): Loans with no significant increase in credit risk. General provision: 1.00%.",
        "  1.2 Stage 2 (Underperforming): Significant increase in credit risk (overdue 30-89 days). Provision: 5.00%.",
        "  1.3 Stage 3 (Non-Performing): Overdue for 90 days or more. Must maintain specific provision.",
        "",
        "2. Effective Date & Compliance Timeline:",
        "The amended provisions shall come into force with effect from 01 January 2025.",
        "All banks must submit an initial readiness report to BRPD within 31 December 2024.",
        "",
        "3. Penal Sanctions:",
        "Failure to comply with these provisions will attract penal actions under Section 109(7) of the Bank Company Act, 1991."
    ]
    y = 585
    for line in lines_p1:
        c_en.drawString(50, y, line)
        y -= 16
    c_en.showPage()

    # Page 2: Table
    c_en.setFont("Helvetica-Bold", 12)
    c_en.drawString(50, 750, "Annexure A: Required Provisioning Schedule")
    c_en.setFont("Helvetica", 10)
    table_lines = [
        "Table 1: Minimum Regulatory Provisioning Requirements",
        "--------------------------------------------------------------------------------",
        "Loan Category               Overdue Period           Minimum Provision Rate",
        "--------------------------------------------------------------------------------",
        "Standard (Continuous)       Not Overdue              1.00 percent",
        "Special Mention Account     30 to 89 days            5.00 percent",
        "Sub-Standard                90 to 179 days           20.00 percent",
        "Doubtful                    180 to 269 days          50.00 percent",
        "Bad or Loss                 270 days or more         100.00 percent",
        "--------------------------------------------------------------------------------"
    ]
    y = 710
    for line in table_lines:
        c_en.drawString(50, y, line)
        y -= 16
    c_en.showPage()
    c_en.save()

    # 2. Legacy Bijoy Encoded PDF
    pdf_bijoy = corpus_dir / "gold_legacy_bijoy.pdf"
    c_b = canvas.Canvas(str(pdf_bijoy), pagesize=letter)
    c_b.setFont("Helvetica", 11)
    c_b.drawString(50, 750, "evsjv‡`k e¨vsK (Bangladesh Bank)")
    c_b.drawString(50, 720, "cÖÁvcb bs- 04/2014")
    c_b.drawString(50, 690, "ZvwiL: 15 GwcÖj 2014")
    c_b.drawString(50, 660, "cÖwZ, e¨e¯’vcbv cwiPvjK / cÖavb wbe©vnx Kg©KZ©v")
    c_b.drawString(50, 640, "evsjv‡`‡k Kvh©iZ mKj Zdwmwj e¨vsK")
    c_b.drawString(50, 600, "welq: FY †kÖwYKiY Ges cÖwfkb msiÿY|")
    c_b.drawString(50, 560, "1. GB wb‡`©kbv 01 †g 2014 n‡Z Kvh©Ki n‡e|")
    c_b.drawString(50, 540, "2. cÖwZ e¨vsK AvMvgx 30 w`‡bi g‡a¨ weeiYx `vwLj Kwi‡e|")
    c_b.showPage()
    c_b.save()

    # 3. Scanned English PDF (image embedded into PDF, NO native text)
    pdf_scanned_en = corpus_dir / "gold_scanned_english.pdf"
    img_en = Image.new("RGB", (1200, 1600), color=(255, 255, 255))
    d_en = ImageDraw.Draw(img_en)
    d_en.text((100, 150), "BANGLADESH BANK", fill=(0, 0, 0))
    d_en.text((100, 200), "Department of Off-site Supervision", fill=(0, 0, 0))
    d_en.text((100, 260), "DOS Circular No. 02/2024", fill=(0, 0, 0))
    d_en.text((100, 320), "Subject: Mandatory Submission of Liquidity Return", fill=(0, 0, 0))
    d_en.text((100, 400), "1. All commercial banks must maintain Cash Reserve Ratio of 4.00 percent.", fill=(0, 0, 0))
    d_en.text((100, 460), "2. Statutory Liquidity Ratio (SLR) must be maintained at 13.00 percent.", fill=(0, 0, 0))
    d_en.text((100, 520), "3. Weekly reporting must be submitted every Thursday by 4:00 PM.", fill=(0, 0, 0))
    img_en.save(pdf_scanned_en, "PDF", resolution=150.0)

    # 4. Scanned Bangla PDF (image embedded into PDF, NO native text)
    pdf_scanned_bn = corpus_dir / "gold_scanned_bangla.pdf"
    img_bn = Image.new("RGB", (1200, 1600), color=(255, 255, 255))
    d_bn = ImageDraw.Draw(img_bn)
    # Check for system Bangla font
    bn_font_path = "/System/Library/Fonts/Supplemental/Bangla Sangam MN.ttc"
    if os.path.exists(bn_font_path):
        bn_font = ImageFont.truetype(bn_font_path, 34)
        d_bn.text((100, 150), "বাংলাদেশ ব্যাংক", font=bn_font, fill=(0, 0, 0))
        d_bn.text((100, 220), "ব্যাংকিং প্রবিধান ও নীতি বিভাগ", font=bn_font, fill=(0, 0, 0))
        d_bn.text((100, 290), "সার্কুলার নং ০৮/২০২৪", font=bn_font, fill=(0, 0, 0))
        d_bn.text((100, 360), "বিষয়: গ্রিন ফাইন্যান্স বিষয়ক নীতিমালা", font=bn_font, fill=(0, 0, 0))
        d_bn.text((100, 440), "১. সকল তফসিলি ব্যাংকের জন্য মোট ঋণের ৫ শতাংশ গ্রিন ফাইন্যান্স নিশ্চিত করতে হবে।", font=bn_font, fill=(0, 0, 0))
        d_bn.text((100, 520), "২. এই নির্দেশনা অবিলম্বে কার্যকর হবে।", font=bn_font, fill=(0, 0, 0))
    else:
        d_bn.text((100, 150), "BANGLADESH BANK BANGLA SCANNED CIRCULAR", fill=(0, 0, 0))
    img_bn.save(pdf_scanned_bn, "PDF", resolution=150.0)

    # 5. Table Heavy Regulatory Document
    pdf_tbl = corpus_dir / "gold_table_heavy_capital.pdf"
    c_tbl = canvas.Canvas(str(pdf_tbl), pagesize=letter)
    c_tbl.setFont("Helvetica-Bold", 14)
    c_tbl.drawString(150, 750, "BANGLADESH BANK - BASEL III GUIDELINES")
    c_tbl.setFont("Helvetica", 10)
    c_tbl.drawString(50, 720, "Table 1: Minimum Capital Requirements and Capital Conservation Buffer")
    c_tbl.drawString(50, 705, "-----------------------------------------------------------------------------------------")
    c_tbl.drawString(50, 690, "Regulatory Component               Minimum Ratio        Regulatory Leverage")
    c_tbl.drawString(50, 675, "-----------------------------------------------------------------------------------------")
    c_tbl.drawString(50, 660, "Common Equity Tier 1 (CET1)        4.50 percent         3.00 percent")
    c_tbl.drawString(50, 645, "Tier 1 Capital Ratio               6.00 percent         4.00 percent")
    c_tbl.drawString(50, 630, "Minimum Total Capital (CRAR)       10.00 percent        5.00 percent")
    c_tbl.drawString(50, 615, "Capital Conservation Buffer        2.50 percent         Not Applicable")
    c_tbl.drawString(50, 600, "-----------------------------------------------------------------------------------------")
    c_tbl.drawString(50, 570, "Table 2: Penal Sanctions for Capital Deficiency")
    c_tbl.drawString(50, 555, "-----------------------------------------------------------------------------------------")
    c_tbl.drawString(50, 540, "Deficiency Level                   Dividend Restriction  Mandatory Recapitalization Period")
    c_tbl.drawString(50, 525, "-----------------------------------------------------------------------------------------")
    c_tbl.drawString(50, 510, "Deficiency < 1.00%                 50% Dividend Payout   90 days")
    c_tbl.drawString(50, 495, "Deficiency >= 1.00%                100% Payout Block     60 days")
    c_tbl.drawString(50, 480, "-----------------------------------------------------------------------------------------")
    c_tbl.showPage()
    c_tbl.save()

    print("Successfully generated all gold benchmark fixtures in backend/app/tests/fixtures/corpus/")


if __name__ == "__main__":
    generate_all_gold_fixtures()
