import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def generate_fixture_pdfs():
    corpus_dir = Path("backend/app/tests/fixtures/corpus")
    corpus_dir.mkdir(parents=True, exist_ok=True)

    # 1. BRPD Circular 15/2024
    pdf_15 = corpus_dir / "bb_brpd_2024_15.pdf"
    c1 = canvas.Canvas(str(pdf_15), pagesize=letter)
    
    # Page 1
    c1.setFont("Helvetica-Bold", 14)
    c1.drawString(200, 750, "BANGLADESH BANK")
    c1.setFont("Helvetica", 11)
    c1.drawString(220, 735, "Head Office, Motijheel, Dhaka")
    c1.drawString(170, 720, "Banking Regulation and Policy Department (BRPD)")
    
    c1.drawString(50, 680, "BRPD Circular No. 15")
    c1.drawString(450, 680, "Date: 27 November 2024")
    c1.drawString(50, 660, "Managing Director / Chief Executive Officer")
    c1.drawString(50, 645, "All Scheduled Commercial Banks operating in Bangladesh")
    
    c1.setFont("Helvetica-Bold", 12)
    c1.drawString(50, 615, "Subject: Master Policy on Loan Classification and Provisioning Alignment with IFRS 9")
    
    c1.setFont("Helvetica", 10)
    text_p1 = [
        "Dear Sir,",
        "Please refer to BRPD Circular No. 14 dated 23 September 2012 and subsequent instructions issued on",
        "loan classification and provisioning standards for scheduled commercial banks.",
        "",
        "With a view to aligning credit risk assessment and asset quality measurement with International",
        "Financial Reporting Standard 9 (IFRS 9: Financial Instruments) and strengthening the risk management",
        "framework of the banking sector, the existing loan classification criteria are hereby amended as follows:",
        "",
        "1. Mandatory Staging Framework:",
        "All scheduled commercial banks must classify their credit facilities into three distinct stages:",
        "  (a) Stage 1 (Performing): Loans with no significant increase in credit risk since initial recognition.",
        "      General provision of 1.00% must be maintained.",
        "  (b) Stage 2 (Underperforming): Loans exhibiting significant increase in credit risk (SICR) or overdue",
        "      past 30 days up to 89 days. General provision of 5.00% must be maintained.",
        "  (c) Stage 3 (Non-Performing): Overdue for 90 days or more. Sub-standard, Doubtful, and Bad/Loss.",
        "",
        "2. Effective Date & Compliance Timeline:",
        "The amended provisions set forth in this Circular shall come into force with effect from 01 January 2025.",
        "All banks must submit an initial readiness report to BRPD within 31 December 2024.",
        "",
        "Please acknowledge receipt.",
        "Yours faithfully,",
        "(Mohammad Shahriar Siddiqui)",
        "Director, Banking Regulation and Policy Department"
    ]
    y = 585
    for line in text_p1:
        c1.drawString(50, y, line)
        y -= 16
    c1.showPage()

    # Page 2
    c1.setFont("Helvetica-Bold", 12)
    c1.drawString(50, 750, "BRPD Circular No. 15/2024 - Annexure: Reporting Template")
    c1.setFont("Helvetica", 10)
    text_p2 = [
        "Table 1: Quarterly Loan Classification & Provisioning Summary (Amount in Crore BDT)",
        "-----------------------------------------------------------------------------------------",
        "Category            Outstanding Balance      Required Provision      Maintained Provision",
        "-----------------------------------------------------------------------------------------",
        "Stage 1 (Normal)          45000.50                 450.00                   450.00",
        "Stage 2 (SMA/Watch)        8200.20                 410.01                   410.01",
        "Stage 3 (NPL - Sub)        1500.00                 300.00                   300.00",
        "Stage 3 (NPL - Doubtful)    950.00                 475.00                   475.00",
        "Stage 3 (NPL - Bad/Loss)   3200.00                3200.00                  3200.00",
        "-----------------------------------------------------------------------------------------",
        "",
        "3. Specific Instructions:",
        "No scheduled bank shall reverse any recognized interest into income on non-performing loans without",
        "explicit prior written approval from Bangladesh Bank.",
        "Failure to comply with these provisions will attract penal actions under Section 109(7) of the",
        "Bank Company Act, 1991."
    ]
    y = 720
    for line in text_p2:
        c1.drawString(50, y, line)
        y -= 16
    c1.showPage()
    c1.save()
    print(f"Generated test fixture: {pdf_15}")

    # 2. BRPD Circular 16/2024
    pdf_16 = corpus_dir / "bb_brpd_2024_16.pdf"
    c2 = canvas.Canvas(str(pdf_16), pagesize=letter)
    c2.setFont("Helvetica-Bold", 14)
    c2.drawString(200, 750, "BANGLADESH BANK")
    c2.setFont("Helvetica", 11)
    c2.drawString(170, 720, "Banking Regulation and Policy Department (BRPD)")
    c2.drawString(50, 680, "BRPD Circular No. 16")
    c2.drawString(450, 680, "Date: 01 December 2024")
    c2.drawString(50, 645, "All Scheduled Commercial Banks and Financial Institutions in Bangladesh")
    c2.setFont("Helvetica-Bold", 12)
    c2.drawString(50, 615, "Subject: Guidelines on Ultimate Beneficial Ownership (UBO) Disclosure")
    c2.setFont("Helvetica", 10)
    text_ubo = [
        "Dear Sir,",
        "To combat trade-based money laundering, illicit financial flows, and willful default through shell corporations,",
        "Bangladesh Bank issues these guidelines under Section 45 of the Bank Company Act, 1991.",
        "",
        "1. Threshold for Ultimate Beneficial Ownership:",
        "Any natural person holding directly or indirectly 10 percent or more equity interest, voting rights, or",
        "controlling management authority in a borrowing entity must be identified as an Ultimate Beneficial Owner (UBO).",
        "",
        "2. Mandatory Obligations:",
        "All scheduled commercial banks must obtain verified UBO declarations and National ID / Passport copies",
        "prior to loan disbursement or renewal of credit lines exceeding BDT 5 Crore.",
        "Banks must submit biannual UBO compliance status reports to BRPD and BFIU within 15 days of each half-year end.",
        "",
        "3. Supersession:",
        "This circular supersedes BRPD Circular Letter No. 05 dated 12 March 2018 on shareholder disclosure.",
        "",
        "Yours faithfully,",
        "(Mohammad Shahriar Siddiqui)",
        "Director, BRPD"
    ]
    y = 585
    for line in text_ubo:
        c2.drawString(50, y, line)
        y -= 16
    c2.showPage()
    c2.save()
    print(f"Generated test fixture: {pdf_16}")


if __name__ == "__main__":
    generate_fixture_pdfs()
