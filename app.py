import io
import os
import sqlite3
import smtplib
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import plotly.express as px
import streamlit as st
from openai import OpenAI
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Smart Invoicer & Debt Collector",
    page_icon="🧾",
    layout="wide",
)

# ============================================================
# DATABASE
# ============================================================

DB_FILE = "invoices.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT,
            customer_name TEXT,
            customer_email TEXT,
            invoice_date TEXT,
            total_amount REAL,
            amount_paid REAL,
            balance REAL,
            status TEXT
        )
        """
    )

    conn.commit()
    conn.close()

def save_invoice_to_db(
    invoice_number,
    customer_name,
    customer_email,
    invoice_date,
    total_amount,
    amount_paid,
    balance,
    status,
):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO invoices (
            invoice_number,
            customer_name,
            customer_email,
            invoice_date,
            total_amount,
            amount_paid,
            balance,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invoice_number,
            customer_name,
            customer_email,
            invoice_date,
            total_amount,
            amount_paid,
            balance,
            status,
        ),
    )

    conn.commit()
    conn.close()

def get_invoice_history():
    conn = sqlite3.connect(DB_FILE)

    df = pd.read_sql_query(
        "SELECT * FROM invoices ORDER BY id DESC",
        conn,
    )

    conn.close()
    return df

init_db()

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_text(value):
    if value is None:
        return ""
    return str(value)

def format_currency(value):
    try:
        return f"₦{float(value):,.2f}"
    except (ValueError, TypeError):
        return "₦0.00"

def clean_items(items):
    cleaned = []

    for item in items:
        description = safe_text(item.get("description", "")).strip()

        if not description:
            continue

        try:
            quantity = float(item.get("quantity", 1))
        except (ValueError, TypeError):
            quantity = 1.0

        try:
            price = float(item.get("price", 0))
        except (ValueError, TypeError):
            price = 0.0

        cleaned.append(
            {
                "description": description,
                "quantity": max(quantity, 0.0),
                "price": max(price, 0.0),
            }
        )

    return cleaned

def calculate_subtotal(items):
    subtotal = 0.0

    for item in items:
        try:
            quantity = float(item.get("quantity", 0))
            price = float(item.get("price", 0))
            subtotal += quantity * price
        except (ValueError, TypeError):
            pass

    return subtotal

# ============================================================
# OPENAI API KEY
# ============================================================

def get_openai_api_key():
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]

        if "OPENAI_KEY" in st.secrets:
            return st.secrets["OPENAI_KEY"]

    except Exception:
        pass

    return os.getenv("OPENAI_API_KEY")

# ============================================================
# PDF INVOICE GENERATOR
# ============================================================

def generate_pdf_invoice(
    business_name,
    business_address,
    business_phone,
    business_email,
    customer_name,
    customer_email,
    customer_phone,
    customer_address,
    invoice_number,
    invoice_date,
    due_date,
    items,
    tax_rate,
    amount_paid,
    notes,
    payment_url="",
):
    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    normal_style = ParagraphStyle(
        "NormalInvoice",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )

    heading_style = ParagraphStyle(
        "HeadingInvoice",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        spaceAfter=6,
    )

    title_style = ParagraphStyle(
        "TitleInvoice",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=22,
        leading=26,
        spaceAfter=12,
    )

    story = []

    # BUSINESS INFORMATION
    if business_name:
        story.append(
            Paragraph(
                f"<b>{safe_text(business_name)}</b>",
                styles["Heading2"],
            )
        )

    if business_address:
        story.append(
            Paragraph(
                safe_text(business_address),
                normal_style,
            )
        )

    if business_phone:
        story.append(
            Paragraph(
                f"Phone: {safe_text(business_phone)}",
                normal_style,
            )
        )

    if business_email:
        story.append(
            Paragraph(
                f"Email: {safe_text(business_email)}",
                normal_style,
            )
        )

    story.append(Spacer(1, 12))

    story.append(
        Paragraph(
            "INVOICE",
            title_style,
        )
    )

    # INVOICE DETAILS
    invoice_details = [
        [
            Paragraph("<b>Invoice Number</b>", normal_style),
            Paragraph(safe_text(invoice_number), normal_style),
        ],
        [
            Paragraph("<b>Invoice Date</b>", normal_style),
            Paragraph(safe_text(invoice_date), normal_style),
        ],
        [
            Paragraph("<b>Due Date</b>", normal_style),
            Paragraph(safe_text(due_date), normal_style),
        ],
    ]

    details_table = Table(
        invoice_details,
        colWidths=[120, 350],
    )

    details_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(details_table)
    story.append(Spacer(1, 16))

    # CUSTOMER
    story.append(
        Paragraph(
            "BILL TO",
            heading_style,
        )
    )

    if customer_name:
        story.append(
            Paragraph(
                f"<b>{safe_text(customer_name)}</b>",
                normal_style,
            )
        )

    if customer_email:
        story.append(
            Paragraph(
                f"Email: {safe_text(customer_email)}",
                normal_style,
            )
        )

    if customer_phone:
        story.append(
            Paragraph(
                f"Phone: {safe_text(customer_phone)}",
                normal_style,
            )
        )

    if customer_address:
        story.append(
            Paragraph(
                safe_text(customer_address),
                normal_style,
            )
        )

    story.append(Spacer(1, 16))

    # ITEMS
    table_data = [
        [
            Paragraph("<b>Description</b>", normal_style),
            Paragraph("<b>Qty</b>", normal_style),
            Paragraph("<b>Unit Price</b>", normal_style),
            Paragraph("<b>Amount</b>", normal_style),
        ]
    ]

    for item in items:
        description = safe_text(item.get("description", ""))
        quantity = float(item.get("quantity", 0))
        price = float(item.get("price", 0))
        amount = quantity * price

        table_data.append(
            [
                Paragraph(description, normal_style),
                Paragraph(f"{quantity:g}", normal_style),
                Paragraph(format_currency(price), normal_style),
                Paragraph(format_currency(amount), normal_style),
            ]
        )

    items_table = Table(
        table_data,
        colWidths=[250, 55, 100, 100],
        repeatRows=1,
    )

    items_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(items_table)
    story.append(Spacer(1, 16))

    # TOTALS
    subtotal = calculate_subtotal(items)

    try:
        tax_rate_value = float(tax_rate)
    except (ValueError, TypeError):
        tax_rate_value = 0.0

    tax_amount = subtotal * tax_rate_value / 100
    total_amount = subtotal + tax_amount

    try:
        paid_amount = float(amount_paid)
    except (ValueError, TypeError):
        paid_amount = 0.0

    balance = max(total_amount - paid_amount, 0.0)

    summary_data = [
        ["Subtotal", format_currency(subtotal)],
        [f"Tax ({tax_rate_value:g}%)", format_currency(tax_amount)],
        ["Total", format_currency(total_amount)],
        ["Amount Paid", format_currency(paid_amount)],
        ["Balance Due", format_currency(balance)],
    ]

    summary_table = Table(
        summary_data,
        colWidths=[390, 115],
        hAlign="RIGHT",
    )

    summary_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BACKGROUND", (0, 2), (-1, 2), colors.lightgrey),
                ("BACKGROUND", (0, 4), (-1, 4), colors.lightgrey),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(summary_table)
    story.append(Spacer(1, 18))

    # NOTES
    if notes:
        story.append(Paragraph("Notes", heading_style))
        story.append(
            Paragraph(
                safe_text(notes).replace("\n", "<br/>"),
                normal_style,
            )
        )
        story.append(Spacer(1, 12))

    # PAYMENT LINK
    if payment_url:
        story.append(Paragraph("Payment Link", heading_style))
        story.append(Paragraph(safe_text(payment_url), normal_style))
        story.append(Spacer(1, 12))

    # FOOTER
    footer_style = ParagraphStyle(
        "FooterInvoice",
        parent=normal_style,
        alignment=TA_CENTER,
        fontSize=9,
    )

    story.append(Paragraph("Thank you for your business.", footer_style))

    document.build(story)
    buffer.seek(0)

    return buffer.getvalue()

# ============================================================
# SEND EMAIL
# ============================================================

def send_invoice_email(
    sender_email,
    app_password,
    recipient_email,
    invoice_number,
    pdf_bytes,
    customer_name,
):
    if not sender_email:
        raise ValueError("Gmail sender email is required.")

    if not app_password:
        raise ValueError("Gmail App Password is required.")

    if not recipient_email:
        raise ValueError("Customer email is required.")

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = recipient_email
    message["Subject"] = f"Invoice {invoice_number}"

    body = (
        f"Dear {customer_name or 'Customer'},\n\n"
        f"Please find attached invoice {invoice_number}.\n\n"
        "Thank you for your business."
    )

    message.attach(MIMEText(body, "plain"))

    attachment = MIMEApplication(
        pdf_bytes,
        _subtype="pdf",
    )

    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=f"{invoice_number}.pdf",
    )

    message.attach(attachment)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, app_password)
        server.send_message(message)

# ============================================================
# SESSION STATE
# ============================================================

if "invoice_items" not in st.session_state:
    st.session_state["invoice_items"] = [
        {
            "description": "Consulting Service",
            "quantity": 1.0,
            "price": 0.0,
        },
        {
            "description": "Software License",
            "quantity": 1.0,
            "price": 0.0,
        },
    ]

if "generated_pdf" not in st.session_state:
    st.session_state["generated_pdf"] = None

if "generated_ai_message" not in st.session_state:
    st.session_state["generated_ai_message"] = ""

# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("⚙️ Business Settings")

business_name = st.sidebar.text_input(
    "Business Name",
    value="Crown Construction Company Nig LTD",
)

business_address = st.sidebar.text_area(
    "Business Address",
    value="",
)

business_phone = st.sidebar.text_input(
    "Business Phone",
    value="",
)

business_email = st.sidebar.text_input(
    "Business Email",
    value="",
)

st.sidebar.file_uploader(
    "Business Logo",
    type=["png", "jpg", "jpeg"],
)

st.sidebar.markdown("---")

st.sidebar.subheader("💳 Payment Settings")

payment_url = st.sidebar.text_input(
    "Paystack Payment Link",
    value="",
)

st.sidebar.markdown("---")

st.sidebar.subheader("📧 Gmail Settings")

gmail_sender = st.sidebar.text_input(
    "Gmail Address",
    value="",
)

gmail_app_password = st.sidebar.text_input(
    "Gmail App Password",
    value="",
    type="password",
)

# ============================================================
# MAIN HEADER
# ============================================================

st.title("🧾 AI Smart Invoicer & Debt Collector")

st.write(
    "Create professional invoices, track payments, "
    "monitor customer debts, send invoices by email, "
    "and generate AI-powered customer messages."
)

# ============================================================
# TABS
# ============================================================

tab1, tab2, tab3 = st.tabs(
    [
        "🧾 Create Invoice",
        "📚 Invoice History",
        "📊 Analytics Dashboard",
    ]
)

# ============================================================
# CREATE INVOICE TAB
# ============================================================

with tab1:
    st.subheader("Customer Information")

    col1, col2 = st.columns(2)

    with col1:
        customer_name = st.text_input("Customer Name")
        customer_email = st.text_input("Customer Email")
        customer_phone = st.text_input("Customer Phone")

    with col2:
        customer_address = st.text_area("Customer Address")
        invoice_number = st.text_input(
            "Invoice Number",
            value=f"INV-{date.today().strftime('%Y%m%d')}",
        )
        invoice_date = st.date_input(
            "Invoice Date",
            value=date.today(),
        )
        due_date = st.date_input(
            "Due Date",
            value=date.today(),
        )

    st.markdown("---")
    st.subheader("Invoice Items")

    updated_items = []

    for index, item in enumerate(st.session_state["invoice_items"]):
        col1, col2, col3, col4 = st.columns([4, 1.5, 2, 1])

        with col1:
            description = st.text_input(
                "Description",
                value=item.get("description", ""),
                key=f"item_description_{index}",
            )

        with col2:
            quantity = st.number_input(
                "Quantity",
                min_value=0.0,
                value=float(item.get("quantity", 1.0)),
                step=1.0,
                key=f"item_quantity_{index}",
            )

        with col3:
            price = st.number_input(
                "Unit Price",
                min_value=0.0,
                value=float(item.get("price", 0.0)),
                step=100.0,
                key=f"item_price_{index}",
            )

        with col4:
            remove_item = st.checkbox(
                "Remove",
                key=f"remove_item_{index}",
            )

        if not remove_item:
            updated_items.append(
                {
                    "description": description,
                    "quantity": quantity,
                    "price": price,
                }
            )

    st.session_state["invoice_items"] = updated_items

    if st.button("➕ Add Another Item"):
        st.session_state["invoice_items"].append(
            {
                "description": "",
                "quantity": 1.0,
                "price": 0.0,
            }
        )
        st.rerun()

    items = clean_items(st.session_state["invoice_items"])

    if not items:
        st.warning("Please add at least one invoice item.")

    st.markdown("---")
    st.subheader("Invoice Summary")

    tax_rate = st.number_input(
        "Tax Rate (%)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.5,
    )

    subtotal = calculate_subtotal(items)
    tax_amount = subtotal * tax_rate / 100
    total_amount = subtotal + tax_amount

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Subtotal", format_currency(subtotal))

    with col2:
        st.metric("Tax", format_currency(tax_amount))

    with col3:
        st.metric("Total", format_currency(total_amount))

    st.markdown("---")
    st.subheader("Payment Status")

    payment_status = st.selectbox(
        "Payment Status",
        ["Unpaid", "Partially Paid", "Paid"],
    )

    if payment_status == "Paid":
        amount_paid = total_amount
    elif payment_status == "Partially Paid":
        amount_paid = st.number_input(
            "Amount Paid",
            min_value=0.0,
            max_value=float(total_amount),
            value=0.0,
            step=100.0,
        )
    else:
        amount_paid = 0.0

    balance = max(total_amount - amount_paid, 0.0)

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Amount Paid", format_currency(amount_paid))

    with col2:
        st.metric("Balance Due", format_currency(balance))

    st.markdown("---")

    notes = st.text_area(
        "Invoice Notes",
        placeholder="Additional notes for the customer...",
    )

    st.markdown("---")
    st.subheader("🔔 Customer Reminder")

    if balance > 0:
        reminder_message = (
            f"Dear {customer_name or 'Customer'}, "
            f"this is a friendly reminder that invoice {invoice_number} "
            f"has an outstanding balance of {format_currency(balance)}."
        )
    else:
        reminder_message = (
            f"Dear {customer_name or 'Customer'}, "
            f"thank you for settling invoice {invoice_number}."
        )

    st.text_area(
        "Suggested Reminder",
        value=reminder_message,
        height=120,
    )

    st.markdown("---")

    # GENERATE PDF
    if st.button(
        "📄 Generate PDF Invoice",
        type="primary",
        use_container_width=True,
    ):
        if not customer_name.strip():
            st.error("Please enter the customer name.")
        elif not items:
            st.error("Please add at least one valid invoice item.")
        else:
            try:
                pdf_bytes = generate_pdf_invoice(
                    business_name=business_name,
                    business_address=business_address,
                    business_phone=business_phone,
                    business_email=business_email,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    customer_phone=customer_phone,
                    customer_address=customer_address,
                    invoice_number=invoice_number,
                    invoice_date=str(invoice_date),
                    due_date=str(due_date),
                    items=items,
                    tax_rate=tax_rate,
                    amount_paid=amount_paid,
                    notes=notes,
                    payment_url=payment_url,
                )

                st.session_state["generated_pdf"] = pdf_bytes
                st.success("PDF invoice generated successfully.")

            except Exception as error:
                st.session_state["generated_pdf"] = None
                st.error(f"PDF generation failed: {type(error).__name__}: {error}")

    if st.session_state["generated_pdf"]:
        st.download_button(
            label="⬇️ Download PDF Invoice",
            data=st.session_state["generated_pdf"],
            file_name=f"{invoice_number}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    st.markdown("---")

    # SAVE INVOICE
    if st.button(
        "💾 Save Invoice to Database",
        use_container_width=True,
    ):
        if not customer_name.strip():
            st.error("Please enter the customer name.")
        elif not items:
            st.error("Please add at least one valid invoice item.")
        else:
            if balance <= 0:
                status = "Paid"
            elif amount_paid > 0:
                status = "Partially Paid"
            else:
                status = "Unpaid"

            try:
                save_invoice_to_db(
                    invoice_number=invoice_number,
                    customer_name=customer_name,
                    customer_email=customer_email,
                    invoice_date=str(invoice_date),
                    total_amount=total_amount,
                    amount_paid=amount_paid,
                    balance=balance,
                    status=status,
                )
                st.success("Invoice saved successfully.")

            except Exception as error:
                st.error(f"Could not save invoice: {type(error).__name__}: {error}")

    st.markdown("---")

    # EMAIL INVOICE
    if st.button(
        "📧 Send Invoice by Email",
        use_container_width=True,
    ):
        if not st.session_state["generated_pdf"]:
            st.error("Generate the PDF invoice first.")
        elif not customer_email.strip():
            st.error("Please enter the customer's email address.")
        elif not gmail_sender.strip():
            st.error("Please enter your Gmail address in the sidebar.")
        elif not gmail_app_password.strip():
            st.error("Please enter your Gmail App Password in the sidebar.")
        else:
            try:
                send_invoice_email(
                    sender_email=gmail_sender,
                    app_password=gmail_app_password,
                    recipient_email=customer_email,
                    invoice_number=invoice_number,
                    pdf_bytes=st.session_state["generated_pdf"],
                    customer_name=customer_name,
                )
                st.success("Invoice email sent successfully.")

            except Exception as error:
                st.error(f"Email sending failed: {type(error).__name__}: {error}")

# ============================================================
# INVOICE HISTORY TAB
# ============================================================

with tab2:
    st.subheader("📚 Invoice History")

    try:
        history_df = get_invoice_history()

        if history_df.empty:
            st.info("No invoices have been saved yet.")
        else:
            display_df = history_df.copy()

            for column in ["total_amount", "amount_paid", "balance"]:
                display_df[column] = display_df[column].apply(format_currency)

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
            )

    except Exception as error:
        st.error(f"Could not load invoice history: {type(error).__name__}: {error}")

# ============================================================
# ANALYTICS TAB
# ============================================================

with tab3:
    st.subheader("📊 Analytics Dashboard")

    try:
        analytics_df = get_invoice_history()

        if analytics_df.empty:
            st.info("Save some invoices first to see analytics.")
        else:
            total_invoiced = analytics_df["total_amount"].sum()
            total_collected = analytics_df["amount_paid"].sum()
            total_debt = analytics_df["balance"].sum()
            invoice_count = len(analytics_df)

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Invoiced", format_currency(total_invoiced))

            with col2:
                st.metric("Total Collected", format_currency(total_collected))

            with col3:
                st.metric("Outstanding Debt", format_currency(total_debt))

            with col4:
                st.metric("Number of Invoices", invoice_count)

            st.markdown("---")

            chart_data = pd.DataFrame(
                {
                    "Category": ["Collected", "Outstanding"],
                    "Amount": [total_collected, total_debt],
                }
            )

            fig_pie = px.pie(
                chart_data,
                names="Category",
                values="Amount",
                title="Collected vs Outstanding",
            )

            st.plotly_chart(fig_pie, use_container_width=True)

            status_data = analytics_df["status"].value_counts().reset_index()
            status_data.columns = ["Status", "Count"]

            fig_bar = px.bar(
                status_data,
                x="Status",
                y="Count",
                title="Invoice Status",
            )

            st.plotly_chart(fig_bar, use_container_width=True)

    except Exception as error:
        st.error(f"Analytics error: {type(error).__name__}: {error}")

# ============================================================
# AI MESSAGE ASSISTANT
# ============================================================

st.markdown("---")

st.header("🤖 AI Message Assistant")

st.write("Generate professional customer messages using AI.")

ai_request = st.text_area(
    "What message do you want to generate?",
    placeholder="Example: Write a polite reminder to a customer who has an overdue invoice.",
)

col1, col2 = st.columns(2)

with col1:
    ai_tone = st.selectbox(
        "Tone",
        ["Professional", "Friendly", "Polite", "Firm", "Short"],
    )

with col2:
    ai_format = st.selectbox(
        "Format",
        ["Email", "WhatsApp Message", "SMS"],
    )

if st.button("🤖 Generate AI Message", use_container_width=True):
    if not ai_request.strip():
        st.warning("Please describe the message you want.")
    else:
        api_key = get_openai_api_key()

        if not api_key:
            st.error("OpenAI API key not found. Please check your Streamlit Secrets.")
        else:
            try:
                client = OpenAI(api_key=api_key)

                prompt = f"""
Create a {ai_format.lower()} for a customer.

Tone: {ai_tone}

User request:
{ai_request}

Make the message clear, professional, and ready to send.
Do not add explanations outside the message.
"""

                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                )

                st.session_state["generated_ai_message"] = (
                    response.choices[0].message.content
                )

                st.success("AI message generated successfully.")

            except Exception as error:
                st.error(f"AI generation failed: {type(error).__name__}: {error}")

if st.session_state["generated_ai_message"]:
    st.text_area(
        "Generated Message",
        value=st.session_state["generated_ai_message"],
        height=220,
    )

# ============================================================
# CUSTOMER FOLLOW-UP
# ============================================================

st.markdown("---")

st.header("📞 Customer Follow-Up")

try:
    followup_df = get_invoice_history()

    if followup_df.empty:
        st.info("There are no saved invoices requiring follow-up.")
    else:
        debt_df = followup_df[followup_df["balance"] > 0].copy()

        if debt_df.empty:
            st.success("No outstanding customer debts.")
        else:
            st.warning(f"{len(debt_df)} invoice(s) have outstanding balances.")

            for _, row in debt_df.iterrows():
                st.write(
                    f"**{row['customer_name']}** — "
                    f"Invoice {row['invoice_number']} — "
                    f"Balance: {format_currency(row['balance'])}"
                )

except Exception as error:
    st.error(f"Follow-up section error: {type(error).__name__}: {error}")

# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption("AI Smart Invoicer & Debt Collector")
