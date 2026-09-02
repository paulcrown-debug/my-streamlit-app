import io
import sqlite3
import smtplib
import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------
# DATABASE INITIALIZATION
# -----------------------------
def init_db():
    conn = sqlite3.connect("invoices.db")
    cursor = conn.cursor()
    cursor.execute("""
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
    """)
    conn.commit()
    conn.close()

def save_invoice_to_db(inv_number, cust_name, cust_email, inv_date, total, paid, balance, status):
    conn = sqlite3.connect("invoices.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO invoices (invoice_number, customer_name, customer_email, invoice_date, total_amount, amount_paid, balance, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (inv_number, cust_name, cust_email, str(inv_date), total, paid, balance, status))
    conn.commit()
    conn.close()

init_db()

# -----------------------------
# PDF GENERATOR FUNCTION
# -----------------------------
def generate_pdf_invoice(biz_data, cust_data, inv_data, items_df, logo_bytes=None, payment_link=""):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        rightMargin=36, 
        leftMargin=36, 
        topMargin=36, 
        bottomMargin=36
    )
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor("#1E293B"), spaceAfter=6
    )

    if logo_bytes:
        try:
            logo_img = Image(io.BytesIO(logo_bytes), width=120, height=50)
            logo_img.hAlign = 'LEFT'
            elements.append(logo_img)
            elements.append(Spacer(1, 10))
        except Exception:
            pass

    elements.append(Paragraph(str(biz_data["name"]), title_style))
    elements.append(Paragraph(f"<b>Email:</b> {biz_data['email']} | <b>Phone:</b> {biz_data['phone']}", styles['Normal']))
    elements.append(Paragraph(f"<b>Address:</b> {biz_data['address']}", styles['Normal']))
    elements.append(Spacer(1, 15))

    info_table_data = [
        [
            Paragraph(f"<b>BILL TO:</b><br/>{cust_data['name']}<br/>{cust_data['address']}<br/>{cust_data['email']}", styles['Normal']),
            Paragraph(f"<b>INVOICE DETAILS:</b><br/><b>Invoice #:</b> {inv_data['number']}<br/><b>Date:</b> {inv_data['date']}<br/><b>Due Date:</b> {inv_data['due_date']}", styles['Normal'])
        ]
    ]
    info_table = Table(info_table_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 10)]))
    elements.append(info_table)
    elements.append(Spacer(1, 15))

    table_data = [["Description", "Qty", "Unit Price (NGN)", "Total (NGN)"]]
    for _, row in items_df.iterrows():
        qty = row.get("Quantity", 1)
        price = row.get("Unit Price (NGN)", 0.0)
        table_data.append([str(row.get("Description", "Item")), str(qty), f"N{price:,.2f}", f"N{(qty * price):,.2f}"])

    items_table = Table(table_data, colWidths=[240, 60, 120, 120])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 15))

    summary_data = [
        ["Subtotal:", f"N{inv_data['subtotal']:,.2f}"],
        ["Tax:", f"N{inv_data['tax']:,.2f}"],
        ["Total Amount:", f"N{inv_data['total']:,.2f}"],
        ["Amount Paid:", f"N{inv_data['amount_paid']:,.2f}"],
        ["Balance Due:", f"N{inv_data['balance']:,.2f}"]
    ]
    summary_table = Table(summary_data, colWidths=[420, 120])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTNAME', (0, 4), (-1, 4), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 4), (-1, 4), colors.HexColor("#DC2626")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(summary_table)

    if payment_link:
        elements.append(Spacer(1, 15))
        elements.append(Paragraph(f"<b>Pay Online:</b> <font color='#0284C7'><u><a href='{payment_link}'>{payment_link}</a></u></font>", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# -----------------------------
# EMAIL SENDER FUNCTION
# -----------------------------
def send_invoice_email(sender_email, sender_password, recipient_email, subject, body_text, pdf_buffer, filename):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body_text, 'plain'))
    attachment = MIMEApplication(pdf_buffer.getvalue(), _subtype="pdf")
    attachment.add_header('Content-Disposition', 'attachment', filename=filename)
    msg.attach(attachment)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(sender_email, sender_password)
    server.sendmail(sender_email, recipient_email, msg.as_string())
    server.quit()

# -----------------------------
# APP INTERFACE
# -----------------------------
st.set_page_config(page_title="AI Smart Invoicer", page_icon="📄", layout="wide")

st.title("📄 AI Smart Invoicer, Analytics & Debt Collector")

# Sidebar
st.sidebar.header("🏢 Business Information")
business_name = st.sidebar.text_input("Business Name", "My Business")
business_email = st.sidebar.text_input("Business Email", "business@example.com")
business_phone = st.sidebar.text_input("Business Phone", "+234 800 000 0000")
business_address = st.sidebar.text_area("Business Address", "Nigeria")

logo_file = st.sidebar.file_uploader("Upload Company Logo", type=["jpg", "png", "jpeg"])
logo_bytes = logo_file.read() if logo_file else None

st.sidebar.divider()
st.sidebar.header("💳 Paystack Settings")
paystack_slug = st.sidebar.text_input("Paystack Custom Page Link (Slug)", "", help="e.g. mybusiness or https://paystack.com/pay/mybusiness")

st.sidebar.divider()
st.sidebar.header("📧 Email Server Config (Gmail)")
smtp_email = st.sidebar.text_input("Sender Gmail", "")
smtp_password = st.sidebar.text_input("App Password", type="password")

# Tabs
tab1, tab2, tab3 = st.tabs(["📄 Create Invoice", "📊 Invoice History", "📈 Analytics Dashboard"])

# TAB 1: CREATE INVOICE
with tab1:
    st.header("👤 Customer Information")
    col1, col2 = st.columns(2)
    with col1:
        customer_name = st.text_input("Customer Name")
    with col2:
        customer_email = st.text_input("Customer Email")
    customer_address = st.text_area("Customer Address")

    st.header("🧾 Invoice Details")
    col1, col2, col3 = st.columns(3)
    with col1:
        invoice_number = st.text_input("Invoice Number", "INV-001")
    with col2:
        invoice_date = st.date_input("Invoice Date", date.today())
    with col3:
        due_date = st.date_input("Due Date", date.today())

    st.header("📦 Multiple Line Items")
    default_items = pd.DataFrame([
        {"Description": "Consulting Service", "Quantity": 1, "Unit Price (NGN)": 50000.0},
        {"Description": "Software License", "Quantity": 2, "Unit Price (NGN)": 15000.0}
    ])
    edited_items = st.data_editor(default_items, num_rows="dynamic")

    edited_items["Total"] = edited_items["Quantity"] * edited_items["Unit Price (NGN)"]
    subtotal = float(edited_items["Total"].sum())
    tax_rate = st.number_input("Tax (%)", min_value=0.0, value=0.0, step=1.0)
    tax = subtotal * (tax_rate / 100)
    total = subtotal + tax

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Subtotal", f"₦{subtotal:,.2f}")
    with col2:
        st.metric("Tax", f"₦{tax:,.2f}")
    with col3:
        st.metric("Total", f"₦{total:,.2f}")

    st.header("💰 Payment Status")
    payment_status = st.selectbox("Status", ["Unpaid", "Partially Paid", "Paid", "Overdue"])
    amount_paid = st.number_input("Amount Paid (₦)", min_value=0.0, value=0.0, step=100.0)
    balance = max(total - amount_paid, 0.0)
    st.metric("Outstanding Balance", f"₦{balance:,.2f}")

    # Payment Link Logic
    payment_url = ""
    if paystack_slug:
        clean_slug = paystack_slug.split('/')[-1]
        payment_url = f"https://paystack.com/pay/{clean_slug}"

    # Reminder
    st.header("🔔 Payment Reminder")
    reminder_text = ""
    if customer_name:
        reminder_text = f"Dear {customer_name},\n\nReminder for invoice {invoice_number}.\nBalance Due: ₦{balance:,.2f}\nDue Date: {due_date.strftime('%d/%m/%Y')}"
        if payment_url:
            reminder_text += f"\n\nPay Online Instantly: {payment_url}"
        reminder_text += f"\n\nBest regards,\n{business_name}"
        st.text_area("Generated Reminder", reminder_text, height=180)

    # Actions
    st.header("📄 Invoice Preview & Actions")
    if st.button("Generate & Process Invoice", type="primary"):
        save_invoice_to_db(invoice_number, customer_name, customer_email, invoice_date, total, amount_paid, balance, payment_status)
        st.success("Invoice recorded in local SQLite database successfully!")

        biz_dict = {"name": business_name, "email": business_email, "phone": business_phone, "address": business_address}
        cust_dict = {"name": customer_name or "N/A", "email": customer_email or "N/A", "address": customer_address or "N/A"}
        inv_dict = {
            "number": invoice_number, "date": invoice_date.strftime('%d/%m/%Y'), "due_date": due_date.strftime('%d/%m/%Y'),
            "subtotal": subtotal, "tax": tax, "total": total, "amount_paid": amount_paid, "balance": balance
        }

        pdf_file = generate_pdf_invoice(biz_dict, cust_dict, inv_dict, edited_items, logo_bytes, payment_url)

        st.download_button(
            label="📥 Download Invoice PDF",
            data=pdf_file,
            file_name=f"Invoice_{invoice_number}.pdf",
            mime="application/pdf"
        )

        if smtp_email and smtp_password and customer_email:
            try:
                send_invoice_email(
                    smtp_email, smtp_password, customer_email, 
                    f"Invoice {invoice_number} from {business_name}", 
                    reminder_text, pdf_file, f"Invoice_{invoice_number}.pdf"
                )
                st.success(f"Email with PDF attachment sent to {customer_email}!")
            except Exception as e:
                st.error(f"Failed to send email: {e}")

# TAB 2: HISTORY
with tab2:
    st.header("📊 Database Invoice History")
    conn = sqlite3.connect("invoices.db")
    df_db = pd.read_sql_query("SELECT * FROM invoices ORDER BY id DESC", conn)
    conn.close()

    if not df_db.empty:
        st.dataframe(df_db, use_container_width=True)
    else:
        st.info("No saved invoices found in database.")

# TAB 3: ANALYTICS
with tab3:
    st.header("📈 Financial Performance & Debt Recovery Analytics")
    conn = sqlite3.connect("invoices.db")
    df_analytics = pd.read_sql_query("SELECT * FROM invoices", conn)
    conn.close()

    if not df_analytics.empty:
        total_revenue = df_analytics["amount_paid"].sum()
        total_outstanding = df_analytics["balance"].sum()
        total_invoiced = df_analytics["total_amount"].sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Invoiced Volume", f"₦{total_invoiced:,.2f}")
        col2.metric("Total Collected Revenue", f"₦{total_revenue:,.2f}")
        col3.metric("Total Uncollected Debt", f"₦{total_outstanding:,.2f}", delta_color="inverse")

        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Payment Status Breakdown")
            status_fig = px.pie(df_analytics, names="status", values="total_amount", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(status_fig, use_container_width=True)

        with col2:
            st.subheader("Top Customers by Debt Balance")
            debtors_df = df_analytics.groupby("customer_name")["balance"].sum().reset_index().sort_values(by="balance", ascending=False)
            bar_fig = px.bar(debtors_df.head(5), x="customer_name", y="balance", labels={"customer_name": "Customer", "balance": "Outstanding Balance (NGN)"}, color_discrete_sequence=["#DC2626"])
            st.plotly_chart(bar_fig, use_container_width=True)
    else:
        st.info("Generate some invoices to view analytics insights!")