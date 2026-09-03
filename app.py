import io
import os
import streamlit as st
from datetime import date
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
gemini_api_key = os.getenv("GEMINI_API_KEY")

# =========================================================
# PAGE SETTINGS
# =========================================================
st.set_page_config(
    page_title="AI Smart Invoicer",
    page_icon="📄",
    layout="wide"
)

# =========================================================
# HEADER
# =========================================================
st.title("📄 AI Smart Invoicer & Debt Collector")
st.write(
    "Generate professional invoices and draft automated AI "
    "follow-ups for overdue clients."
)

# =========================================================
# API KEY STATUS
# =========================================================
if api_key:
    st.success("API key loaded successfully")
else:
    st.error("API key not found. Please check your .env file")

# =========================================================
# SIDEBAR - BUSINESS INFORMATION
# =========================================================
st.sidebar.header("🏢 Your Business Info")

business_name = st.sidebar.text_input(
    "Business Name",
    "My Freelance Business"
)

business_address = st.sidebar.text_area(
    "Business Address",
    "123 Business Street, Nigeria"
)

business_phone = st.sidebar.text_input(
    "Phone Number",
    "+234 800 000 0000"
)

business_email = st.sidebar.text_input(
    "Business Email",
    "business@example.com"
)

# =========================================================
# CUSTOMER INFORMATION
# =========================================================
st.header("👤 Customer Information")

col1, col2 = st.columns(2)

with col1:
    customer_name = st.text_input(
        "Customer Name",
        placeholder="Enter customer's name"
    )

    customer_email = st.text_input(
        "Customer Email",
        placeholder="customer@example.com"
    )

with col2:
    customer_address = st.text_area(
        "Customer Address",
        placeholder="Enter customer's address"
    )

    customer_phone = st.text_input(
        "Customer Phone",
        placeholder="+234..."
    )

# =========================================================
# INVOICE INFORMATION
# =========================================================
st.header("🧾 Invoice Information")

col1, col2, col3 = st.columns(3)

with col1:
    invoice_number = st.text_input(
        "Invoice Number",
        "INV-001"
    )

with col2:
    invoice_date = st.date_input(
        "Invoice Date",
        date.today()
    )

with col3:
    due_date = st.date_input(
        "Due Date",
        date.today()
    )

# =========================================================
# ITEMS
# =========================================================
st.subheader("📦 Invoice Items")

if "items" not in st.session_state:
    st.session_state["items"] = [
        {
            "description": "",
            "quantity": 1,
            "price": 0.0
        }
    ]

total = 0.0

for i, item in enumerate(st.session_state["items"]):

    col1, col2, col3, col4 = st.columns([4, 1, 2, 2])

    with col1:
        item["description"] = st.text_input(
            "Description",
            value=item["description"],
            key=f"description_{i}"
        )

    with col2:
        item["quantity"] = st.number_input(
            "Qty",
            min_value=1,
            value=item["quantity"],
            key=f"quantity_{i}"
        )

    with col3:
        item["price"] = st.number_input(
            "Unit Price (₦)",
            min_value=0.0,
            value=float(item["price"]),
            key=f"price_{i}"
        )

    subtotal = item["quantity"] * item["price"]
    total += subtotal

    with col4:
        st.write("")
        st.write("")
        st.write(f"**₦{subtotal:,.2f}**")

if st.button("➕ Add Another Item"):
    st.session_state["items"].append(
        {
            "description": "",
            "quantity": 1,
            "price": 0.0
        }
    )
    st.rerun()

# =========================================================
# TOTAL
# =========================================================
st.divider()

col1, col2 = st.columns([3, 1])

with col2:
    st.subheader("Invoice Total")
    st.metric(
        "Total",
        f"₦{total:,.2f}"
    )

# =========================================================
# NOTES
# =========================================================
st.header("📝 Invoice Notes")

notes = st.text_area(
    "Additional Notes",
    placeholder="Thank you for your business..."
)

# =========================================================
# PDF GENERATOR
# =========================================================
def generate_pdf_invoice(
    biz_data,
    cust_data,
    inv_data
):
    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontSize=22,
        spaceAfter=15
    )

    normal_style = styles["Normal"]

    story = []

    story.append(
        Paragraph(
            biz_data["name"],
            title_style
        )
    )

    story.append(
        Paragraph(
            biz_data["address"],
            normal_style
        )
    )

    story.append(
        Paragraph(
            f"Phone: {biz_data['phone']} | "
            f"Email: {biz_data['email']}",
            normal_style
        )
    )

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            f"<b>INVOICE</b> #{inv_data['number']}",
            styles["Heading2"]
        )
    )

    story.append(
        Paragraph(
            f"Invoice Date: {inv_data['invoice_date']}<br/>"
            f"Due Date: {inv_data['due_date']}",
            normal_style
        )
    )

    story.append(Spacer(1, 15))

    story.append(
        Paragraph(
            "<b>Bill To:</b><br/>"
            f"{cust_data['name']}<br/>"
            f"{cust_data['address']}<br/>"
            f"{cust_data['email']}<br/>"
            f"{cust_data['phone']}",
            normal_style
        )
    )

    story.append(Spacer(1, 20))

    table_data = [
        ["Description", "Qty", "Unit Price", "Amount"]
    ]

    for item in inv_data["items"]:
        amount = item["quantity"] * item["price"]

        table_data.append([
            item["description"],
            str(item["quantity"]),
            f"₦{item['price']:,.2f}",
            f"₦{amount:,.2f}"
        ])

    table_data.append([
        "",
        "",
        "TOTAL",
        f"₦{inv_data['total']:,.2f}"
    ])

    table = Table(
        table_data,
        colWidths=[250, 50, 90, 90]
    )

    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (-2, -1), (-1, -1), "Helvetica-Bold"),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
        ])
    )

    story.append(table)

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            f"<b>Notes:</b> {inv_data['notes']}",
            normal_style
        )
    )

    story.append(Spacer(1, 30))

    story.append(
        Paragraph(
            "Thank you for your business!",
            normal_style
        )
    )

    document.build(story)

    buffer.seek(0)

    return buffer

# =========================================================
# GENERATE PDF
# =========================================================
st.header("📥 Generate Invoice")

if st.button("Generate PDF Invoice", type="primary"):

    if not customer_name:
        st.warning("Please enter the customer's name.")

    elif not any(
        item["description"].strip()
        for item in st.session_state.items
    ):
        st.warning("Please add at least one invoice item.")

    else:

        biz_data = {
            "name": business_name,
            "address": business_address,
            "phone": business_phone,
            "email": business_email
        }

        cust_data = {
            "name": customer_name,
            "address": customer_address,
            "email": customer_email,
            "phone": customer_phone
        }

        inv_data = {
            "number": invoice_number,
            "invoice_date": invoice_date,
            "due_date": due_date,
            "items": st.session_state.items,
            "total": total,
            "notes": notes
        }

        pdf = generate_pdf_invoice(
            biz_data,
            cust_data,
            inv_data
        )

        st.success("Invoice created successfully! ✅")

        st.download_button(
            label="⬇️ Download PDF Invoice",
            data=pdf,
            file_name=f"{invoice_number}.pdf",
            mime="application/pdf"
        )

# =========================================================
# EMAIL / DEBT COLLECTION
# =========================================================
st.divider()

st.header("📧 Customer Follow-Up")

followup_type = st.selectbox(
    "Follow-up Type",
    [
        "Payment Reminder",
        "Overdue Payment",
        "Thank You Message"
    ]
)

if followup_type == "Payment Reminder":
    default_message = (
        f"Dear {customer_name or 'Customer'},\n\n"
        f"This is a friendly reminder regarding invoice "
        f"{invoice_number}, which is due on {due_date}.\n\n"
        f"Amount due: ₦{total:,.2f}\n\n"
        "Thank you."
    )

elif followup_type == "Overdue Payment":
    default_message = (
        f"Dear {customer_name or 'Customer'},\n\n"
        f"We would like to remind you that invoice "
        f"{invoice_number} has an outstanding balance of "
        f"₦{total:,.2f}.\n\n"
        "Please arrange payment at your earliest convenience.\n\n"
        "Thank you."
    )

else:
    default_message = (
        f"Dear {customer_name or 'Customer'},\n\n"
        "Thank you for doing business with us. "
        "We sincerely appreciate your support.\n\n"
        "We look forward to working with you again."
    )

email_subject = st.text_input(
    "Email Subject",
    f"{followup_type} - {invoice_number}"
)

email_message = st.text_area(
    "Email Message",
    default_message,
    height=220
)

if st.button("📋 Prepare Email"):
    st.success("Email message prepared successfully.")
    st.code(
        f"To: {customer_email}\n"
        f"Subject: {email_subject}\n\n"
        f"{email_message}"
    )

# =========================================================
# AI SECTION
# =========================================================
st.divider()

st.header("🤖 AI Message Assistant")

st.write(
    "Use this section to prepare a professional message "
    "for your customer."
)

ai_request = st.text_area(
    "What should the AI write?",
    placeholder=(
        "Example: Write a polite message asking a customer "
        "to pay an overdue invoice."
    )
)

if st.button("✨ Generate AI Message"):

    if not api_key:
        st.error(
            "OpenAI API key is not available. "
            "Please check your .env file."
        )

    elif not ai_request.strip():
        st.warning("Please enter what you want the AI to write.")

    else:
        st.info(
            "Your OpenAI API key is connected. "
            "The AI message feature is ready to be connected "
            "to the OpenAI API."
        )

        st.write(
            "Request received:"
        )

        st.write(ai_request)

# =========================================================
# FOOTER
# =========================================================
st.divider()

st.caption(
    "📄 AI Smart Invoicer & Debt Collector"
)