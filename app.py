import io
import sqlite3
import smtplib
import hashlib
import hmac
import secrets
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import plotly.express as px
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Smart Invoicer & Debt Collector",
    page_icon="🧾",
    layout="wide",
)


# ============================================================
# CURRENCY SETTINGS
# ============================================================

CURRENCIES = {
    "🇳🇬 Nigerian Naira (NGN)": {"code": "NGN", "symbol": "₦"},
    "🇺🇸 US Dollar (USD)": {"code": "USD", "symbol": "$"},
    "🇬🇧 British Pound (GBP)": {"code": "GBP", "symbol": "£"},
    "🇪🇺 Euro (EUR)": {"code": "EUR", "symbol": "€"},
    "🇨🇦 Canadian Dollar (CAD)": {"code": "CAD", "symbol": "C$"},
    "🇦🇺 Australian Dollar (AUD)": {"code": "AUD", "symbol": "A$"},
    "🇿🇦 South African Rand (ZAR)": {"code": "ZAR", "symbol": "R"},
    "🇬🇭 Ghanaian Cedi (GHS)": {"code": "GHS", "symbol": "GH₵"},
    "🇰🇪 Kenyan Shilling (KES)": {"code": "KES", "symbol": "KSh"},
    "🇮🇳 Indian Rupee (INR)": {"code": "INR", "symbol": "₹"},
    "🇨🇳 Chinese Yuan (CNY)": {"code": "CNY", "symbol": "¥"},
    "🇯🇵 Japanese Yen (JPY)": {"code": "JPY", "symbol": "¥"},
    "🇦🇪 UAE Dirham (AED)": {"code": "AED", "symbol": "د.إ"},
    "🇸🇦 Saudi Riyal (SAR)": {"code": "SAR", "symbol": "﷼"},
    "🇳🇿 New Zealand Dollar (NZD)": {"code": "NZD", "symbol": "NZ$"},
    "🇸🇬 Singapore Dollar (SGD)": {"code": "SGD", "symbol": "S$"},
    "🇨🇭 Swiss Franc (CHF)": {"code": "CHF", "symbol": "CHF"},
    "🇳🇴 Norwegian Krone (NOK)": {"code": "NOK", "symbol": "kr"},
    "🇸🇪 Swedish Krona (SEK)": {"code": "SEK", "symbol": "kr"},
    "🇧🇷 Brazilian Real (BRL)": {"code": "BRL", "symbol": "R$"},
}


def get_currency_symbol(currency_code):
    for currency in CURRENCIES.values():
        if currency["code"] == currency_code:
            return currency["symbol"]

    return "₦"


def format_currency(value, currency_symbol="₦"):
    try:
        return f"{currency_symbol}{float(value):,.2f}"

    except (ValueError, TypeError):
        return f"{currency_symbol}0.00"


# ============================================================
# DATABASE
# ============================================================

DB_FILE = "invoices.db"


def get_db_connection():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

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
            status TEXT,
            currency_code TEXT DEFAULT 'NGN'
        )
        """
    )

    cursor.execute(
        "PRAGMA table_info(invoices)"
    )

    columns = [
        row[1]
        for row in cursor.fetchall()
    ]

    if "currency_code" not in columns:
        cursor.execute(
            """
            ALTER TABLE invoices
            ADD COLUMN currency_code TEXT DEFAULT 'NGN'
            """
        )

    cursor.execute(
        """
        UPDATE invoices
        SET currency_code = 'NGN'
        WHERE currency_code IS NULL
           OR currency_code = ''
        """
    )

    conn.commit()
    conn.close()


init_db()


# ============================================================
# PASSWORD SECURITY
# ============================================================

def hash_password(password):
    salt = secrets.token_bytes(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200000,
    )

    return (
        salt.hex()
        + ":"
        + password_hash.hex()
    )


def verify_password(password, stored_password):
    try:
        salt_hex, hash_hex = stored_password.split(":")

        salt = bytes.fromhex(salt_hex)
        stored_hash = bytes.fromhex(hash_hex)

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            200000,
        )

        return hmac.compare_digest(
            password_hash,
            stored_hash,
        )

    except (ValueError, TypeError):
        return False


# ============================================================
# USER ACCOUNT FUNCTIONS
# ============================================================

def create_user(username, password):

    username = username.strip()

    password_hash = hash_password(password)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users (
                username,
                password_hash,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                username,
                password_hash,
                str(date.today()),
            ),
        )

        conn.commit()

        return True, "Account created successfully."

    except sqlite3.IntegrityError:

        return False, "That username already exists."

    except Exception as error:

        return (
            False,
            f"Could not create account: "
            f"{type(error).__name__}: {error}",
        )

    finally:
        conn.close()


def authenticate_user(username, password):

    username = username.strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT username, password_hash
        FROM users
        WHERE username = ?
        """,
        (username,),
    )

    user = cursor.fetchone()

    conn.close()

    if not user:
        return False

    return verify_password(
        password,
        user[1],
    )


# ============================================================
# LOGIN / SIGN-UP PAGE
# ============================================================

def show_authentication_page():

    st.markdown(
        """
        <style>
        .auth-title {
            text-align: center;
            font-size: 32px;
            font-weight: bold;
        }

        .auth-subtitle {
            text-align: center;
            font-size: 17px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="auth-title">🧾 Smart Invoicer & Debt Collector</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="auth-subtitle">Secure Business Invoice Management</div>',
        unsafe_allow_html=True,
    )

    st.write("")

    login_tab, signup_tab = st.tabs(
        [
            "🔐 Login",
            "📝 Sign Up",
        ]
    )

    # ========================================================
    # LOGIN
    # ========================================================

    with login_tab:

        st.subheader(
            "🔐 Login to Your Account"
        )

        login_username = st.text_input(
            "Username",
            key="login_username",
        )

        login_password = st.text_input(
            "Password",
            type="password",
            key="login_password",
        )

        if st.button(
            "🔐 Login",
            type="primary",
            use_container_width=True,
        ):

            if not login_username.strip():

                st.error(
                    "Please enter your username."
                )

            elif not login_password:

                st.error(
                    "Please enter your password."
                )

            elif authenticate_user(
                login_username,
                login_password,
            ):

                st.session_state[
                    "authenticated"
                ] = True

                st.session_state[
                    "username"
                ] = login_username.strip()

                st.success(
                    "Login successful."
                )

                st.rerun()

            else:

                st.error(
                    "Invalid username or password."
                )

    # ========================================================
    # SIGN UP
    # ========================================================

    with signup_tab:

        st.subheader(
            "📝 Create a New Account"
        )

        signup_username = st.text_input(
            "Choose a Username",
            key="signup_username",
        )

        signup_password = st.text_input(
            "Create Password",
            type="password",
            key="signup_password",
        )

        signup_confirm_password = st.text_input(
            "Confirm Password",
            type="password",
            key="signup_confirm_password",
        )

        st.info(
            "Password must contain at least 8 characters."
        )

        if st.button(
            "📝 Create Account",
            type="primary",
            use_container_width=True,
        ):

            username = signup_username.strip()
            password = signup_password
            confirm_password = signup_confirm_password

            if not username:

                st.error(
                    "Please choose a username."
                )

            elif len(username) < 3:

                st.error(
                    "Username must contain at least 3 characters."
                )

            elif " " in username:

                st.error(
                    "Username cannot contain spaces."
                )

            elif not password:

                st.error(
                    "Please create a password."
                )

            elif len(password) < 8:

                st.error(
                    "Password must contain at least 8 characters."
                )

            elif password != confirm_password:

                st.error(
                    "Passwords do not match."
                )

            else:

                success, message = create_user(
                    username,
                    password,
                )

                if success:

                    st.success(
                        "Account created successfully! "
                        "Please go to the Login tab and sign in."
                    )

                else:

                    st.error(message)


# ============================================================
# SESSION AUTHENTICATION
# ============================================================

if "authenticated" not in st.session_state:

    st.session_state[
        "authenticated"
    ] = False


if "username" not in st.session_state:

    st.session_state[
        "username"
    ] = ""


if not st.session_state["authenticated"]:

    show_authentication_page()

    st.stop()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def save_invoice_to_db(
    invoice_number,
    customer_name,
    customer_email,
    invoice_date,
    total_amount,
    amount_paid,
    balance,
    status,
    currency_code,
):

    conn = get_db_connection()
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
            status,
            currency_code
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            currency_code,
        ),
    )

    conn.commit()
    conn.close()


def get_invoice_history():

    conn = get_db_connection()

    df = pd.read_sql_query(
        """
        SELECT *
        FROM invoices
        ORDER BY id DESC
        """,
        conn,
    )

    conn.close()

    if "currency_code" in df.columns:

        df["currency_code"] = (
            df["currency_code"]
            .fillna("NGN")
            .replace("", "NGN")
        )

    return df


def safe_text(value):

    if value is None:
        return ""

    return str(value)


def clean_items(items):

    cleaned = []

    for item in items:

        description = safe_text(
            item.get("description", "")
        ).strip()

        if not description:
            continue

        try:

            quantity = float(
                item.get("quantity", 1)
            )

        except (ValueError, TypeError):

            quantity = 1.0

        try:

            price = float(
                item.get("price", 0)
            )

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

            quantity = float(
                item.get("quantity", 0)
            )

            price = float(
                item.get("price", 0)
            )

            subtotal += quantity * price

        except (ValueError, TypeError):

            pass

    return subtotal


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
    currency_symbol="₦",
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

    # ========================================================
    # BUSINESS INFORMATION
    # ========================================================

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

    story.append(
        Spacer(1, 12)
    )

    story.append(
        Paragraph(
            "INVOICE",
            title_style,
        )
    )

    # ========================================================
    # INVOICE DETAILS
    # ========================================================

    invoice_details = [
        [
            Paragraph(
                "<b>Invoice Number</b>",
                normal_style,
            ),
            Paragraph(
                safe_text(invoice_number),
                normal_style,
            ),
        ],
        [
            Paragraph(
                "<b>Invoice Date</b>",
                normal_style,
            ),
            Paragraph(
                safe_text(invoice_date),
                normal_style,
            ),
        ],
        [
            Paragraph(
                "<b>Due Date</b>",
                normal_style,
            ),
            Paragraph(
                safe_text(due_date),
                normal_style,
            ),
        ],
        [
            Paragraph(
                "<b>Currency</b>",
                normal_style,
            ),
            Paragraph(
                safe_text(currency_symbol),
                normal_style,
            ),
        ],
    ]

    details_table = Table(
        invoice_details,
        colWidths=[120, 350],
    )

    details_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.lightgrey,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    story.append(details_table)

    story.append(
        Spacer(1, 16)
    )

    # ========================================================
    # CUSTOMER
    # ========================================================

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

    story.append(
        Spacer(1, 16)
    )

    # ========================================================
    # ITEMS
    # ========================================================

    table_data = [
        [
            Paragraph(
                "<b>Description</b>",
                normal_style,
            ),
            Paragraph(
                "<b>Qty</b>",
                normal_style,
            ),
            Paragraph(
                f"<b>Unit Price ({currency_symbol})</b>",
                normal_style,
            ),
            Paragraph(
                f"<b>Amount ({currency_symbol})</b>",
                normal_style,
            ),
        ]
    ]

    for item in items:

        description = safe_text(
            item.get("description", "")
        )

        quantity = float(
            item.get("quantity", 0)
        )

        price = float(
            item.get("price", 0)
        )

        amount = quantity * price

        table_data.append(
            [
                Paragraph(
                    description,
                    normal_style,
                ),
                Paragraph(
                    f"{quantity:g}",
                    normal_style,
                ),
                Paragraph(
                    format_currency(
                        price,
                        currency_symbol,
                    ),
                    normal_style,
                ),
                Paragraph(
                    format_currency(
                        amount,
                        currency_symbol,
                    ),
                    normal_style,
                ),
            ]
        )

    items_table = Table(
        table_data,
        colWidths=[
            230,
            50,
            110,
            115,
        ],
        repeatRows=1,
    )

    items_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.lightgrey,
                ),
                (
                    "ALIGN",
                    (1, 1),
                    (-1, -1),
                    "RIGHT",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    story.append(items_table)

    story.append(
        Spacer(1, 16)
    )

    # ========================================================
    # TOTALS
    # ========================================================

    subtotal = calculate_subtotal(items)

    try:

        tax_rate_value = float(tax_rate)

    except (ValueError, TypeError):

        tax_rate_value = 0.0

    tax_amount = (
        subtotal * tax_rate_value / 100
    )

    total_amount = (
        subtotal + tax_amount
    )

    try:

        paid_amount = float(amount_paid)

    except (ValueError, TypeError):

        paid_amount = 0.0

    balance = max(
        total_amount - paid_amount,
        0.0,
    )

    summary_data = [
        [
            "Subtotal",
            format_currency(
                subtotal,
                currency_symbol,
            ),
        ],
        [
            f"Tax ({tax_rate_value:g}%)",
            format_currency(
                tax_amount,
                currency_symbol,
            ),
        ],
        [
            "Total",
            format_currency(
                total_amount,
                currency_symbol,
            ),
        ],
        [
            "Amount Paid",
            format_currency(
                paid_amount,
                currency_symbol,
            ),
        ],
        [
            "Balance Due",
            format_currency(
                balance,
                currency_symbol,
            ),
        ],
    ]

    summary_table = Table(
        summary_data,
        colWidths=[390, 115],
        hAlign="RIGHT",
    )

    summary_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (1, -1),
                    "RIGHT",
                ),
                (
                    "BACKGROUND",
                    (0, 2),
                    (-1, 2),
                    colors.lightgrey,
                ),
                (
                    "BACKGROUND",
                    (0, 4),
                    (-1, 4),
                    colors.lightgrey,
                ),
                (
                    "FONTNAME",
                    (0, 2),
                    (-1, 2),
                    "Helvetica-Bold",
                ),
                (
                    "FONTNAME",
                    (0, 4),
                    (-1, 4),
                    "Helvetica-Bold",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    story.append(summary_table)

    story.append(
        Spacer(1, 18)
    )

    # ========================================================
    # NOTES
    # ========================================================

    if notes:

        story.append(
            Paragraph(
                "Notes",
                heading_style,
            )
        )

        story.append(
            Paragraph(
                safe_text(notes).replace(
                    "\n",
                    "<br/>",
                ),
                normal_style,
            )
        )

        story.append(
            Spacer(1, 12)
        )

    # ========================================================
    # PAYMENT LINK
    # ========================================================

    if payment_url:

        story.append(
            Paragraph(
                "Payment Link",
                heading_style,
            )
        )

        story.append(
            Paragraph(
                safe_text(payment_url),
                normal_style,
            )
        )

        story.append(
            Spacer(1, 12)
        )

    # ========================================================
    # FOOTER
    # ========================================================

    footer_style = ParagraphStyle(
        "FooterInvoice",
        parent=normal_style,
        alignment=TA_CENTER,
        fontSize=9,
    )

    story.append(
        Paragraph(
            "Thank you for your business.",
            footer_style,
        )
    )

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

    # Clean the values before using them.
    sender_email = safe_text(
        sender_email
    ).strip()

    app_password = safe_text(
        app_password
    ).strip()

    recipient_email = safe_text(
        recipient_email
    ).strip()

    if not sender_email:

        raise ValueError(
            "Your Gmail address is required in Gmail Settings."
        )

    if not app_password:

        raise ValueError(
            "Your Gmail App Password is required in Gmail Settings."
        )

    if not recipient_email:

        raise ValueError(
            "The customer's email address is required."
        )

    if "@" not in sender_email:

        raise ValueError(
            "Please enter a valid Gmail address."
        )

    if "@" not in recipient_email:

        raise ValueError(
            "Please enter a valid customer email address."
        )

    message = MIMEMultipart()

    message["From"] = sender_email

    message["To"] = recipient_email

    message["Subject"] = (
        f"Invoice {invoice_number}"
    )

    body = (
        f"Dear {customer_name or 'Customer'},\n\n"
        f"Please find attached invoice "
        f"{invoice_number}.\n\n"
        "Thank you for your business."
    )

    message.attach(
        MIMEText(
            body,
            "plain",
        )
    )

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

    try:

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=30,
        ) as server:

            server.login(
                sender_email,
                app_password,
            )

            server.send_message(
                message
            )

    except smtplib.SMTPAuthenticationError as error:

        raise ValueError(
            "Gmail authentication failed. "
            "Make sure you are using your Gmail address "
            "and a Google App Password, not your normal "
            "Gmail password."
        ) from error

    except smtplib.SMTPException as error:

        raise ValueError(
            f"Gmail could not send the invoice: {error}"
        ) from error


# ============================================================
# MAIN APPLICATION SESSION STATE
# ============================================================

if "invoice_items" not in st.session_state:

    st.session_state[
        "invoice_items"
    ] = [
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

    st.session_state[
        "generated_pdf"
    ] = None


if "generated_pdf_currency" not in st.session_state:

    st.session_state[
        "generated_pdf_currency"
    ] = "NGN"


# ============================================================
# IMPORTANT GMAIL SESSION SETTINGS
# ============================================================

if "gmail_sender" not in st.session_state:

    st.session_state[
        "gmail_sender"
    ] = ""


if "gmail_app_password" not in st.session_state:

    st.session_state[
        "gmail_app_password"
    ] = ""


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title(
    "⚙️ Business Settings"
)

st.sidebar.write(
    f"👤 Logged in as: "
    f"**{st.session_state['username']}**"
)


if st.sidebar.button(
    "🚪 Logout",
    use_container_width=True,
):

    st.session_state[
        "authenticated"
    ] = False

    st.session_state[
        "username"
    ] = ""

    st.session_state[
        "generated_pdf"
    ] = None

    st.session_state[
        "gmail_sender"
    ] = ""

    st.session_state[
        "gmail_app_password"
    ] = ""

    st.rerun()


st.sidebar.markdown("---")


# ============================================================
# CURRENCY SELECTOR
# ============================================================

currency_name = st.sidebar.selectbox(
    "💱 Currency",
    list(CURRENCIES.keys()),
    index=0,
)

currency_symbol = CURRENCIES[
    currency_name
]["symbol"]

currency_code = CURRENCIES[
    currency_name
]["code"]


st.sidebar.info(
    f"Selected currency: "
    f"**{currency_code} ({currency_symbol})**"
)


st.sidebar.markdown("---")


# ============================================================
# BUSINESS INFORMATION
# ============================================================

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
    type=[
        "png",
        "jpg",
        "jpeg",
    ],
)


st.sidebar.markdown("---")


# ============================================================
# PAYMENT SETTINGS
# ============================================================

st.sidebar.subheader(
    "💳 Payment Settings"
)


payment_url = st.sidebar.text_input(
    "Paystack Payment Link",
    value="",
)


st.sidebar.markdown("---")


# ============================================================
# GMAIL SETTINGS
# ============================================================

st.sidebar.subheader(
    "📧 Gmail Settings"
)


st.sidebar.caption(
    "Enter YOUR Gmail account here. "
    "This account will send the invoice to your customer."
)


gmail_sender = st.sidebar.text_input(
    "Your Gmail Address (Sender)",
    key="gmail_sender",
    placeholder="yourname@gmail.com",
)


gmail_app_password = st.sidebar.text_input(
    "Your Gmail App Password",
    key="gmail_app_password",
    type="password",
    placeholder="16-character Google App Password",
)


st.sidebar.caption(
    "Use a Google App Password, not your normal Gmail password."
)


st.sidebar.info(
    "Customer email → enter it in Customer Information below."
)


# ============================================================
# MAIN HEADER
# ============================================================

st.title(
    "🧾 Smart Invoicer & Debt Collector"
)

st.write(
    "Create professional invoices, track payments, "
    "monitor customer debts, and send invoices by email."
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

    st.subheader(
        "Customer Information"
    )

    col1, col2 = st.columns(2)

    with col1:

        customer_name = st.text_input(
            "Customer Name"
        )

        customer_email = st.text_input(
            "Customer Email"
        )

        customer_phone = st.text_input(
            "Customer Phone"
        )

    with col2:

        customer_address = st.text_area(
            "Customer Address"
        )

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


    st.subheader(
        "Invoice Items"
    )


    updated_items = []


    for index, item in enumerate(
        st.session_state["invoice_items"]
    ):

        col1, col2, col3, col4 = st.columns(
            [4, 1.5, 2, 1]
        )

        with col1:

            description = st.text_input(
                "Description",
                value=item.get(
                    "description",
                    "",
                ),
                key=f"item_description_{index}",
            )

        with col2:

            quantity = st.number_input(
                "Quantity",
                min_value=0.0,
                value=float(
                    item.get(
                        "quantity",
                        1.0,
                    )
                ),
                step=1.0,
                key=f"item_quantity_{index}",
            )

        with col3:

            price = st.number_input(
                f"Unit Price ({currency_symbol})",
                min_value=0.0,
                value=float(
                    item.get(
                        "price",
                        0.0,
                    )
                ),
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


    st.session_state[
        "invoice_items"
    ] = updated_items


    if st.button(
        "➕ Add Another Item"
    ):

        st.session_state[
            "invoice_items"
        ].append(
            {
                "description": "",
                "quantity": 1.0,
                "price": 0.0,
            }
        )

        st.rerun()


    items = clean_items(
        st.session_state["invoice_items"]
    )


    if not items:

        st.warning(
            "Please add at least one invoice item."
        )


    st.markdown("---")


    st.subheader(
        "Invoice Summary"
    )


    tax_rate = st.number_input(
        "Tax Rate (%)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.5,
    )


    subtotal = calculate_subtotal(
        items
    )


    tax_amount = (
        subtotal * tax_rate / 100
    )


    total_amount = (
        subtotal + tax_amount
    )


    col1, col2, col3 = st.columns(3)


    with col1:

        st.metric(
            "Subtotal",
            format_currency(
                subtotal,
                currency_symbol,
            ),
        )


    with col2:

        st.metric(
            "Tax",
            format_currency(
                tax_amount,
                currency_symbol,
            ),
        )


    with col3:

        st.metric(
            "Total",
            format_currency(
                total_amount,
                currency_symbol,
            ),
        )


    st.markdown("---")


    st.subheader(
        "Payment Status"
    )


    payment_status = st.selectbox(
        "Payment Status",
        [
            "Unpaid",
            "Partially Paid",
            "Paid",
        ],
    )


    if payment_status == "Paid":

        amount_paid = total_amount


    elif payment_status == "Partially Paid":

        amount_paid = st.number_input(
            f"Amount Paid ({currency_symbol})",
            min_value=0.0,
            max_value=float(total_amount),
            value=0.0,
            step=100.0,
        )


    else:

        amount_paid = 0.0


    balance = max(
        total_amount - amount_paid,
        0.0,
    )


    col1, col2 = st.columns(2)


    with col1:

        st.metric(
            "Amount Paid",
            format_currency(
                amount_paid,
                currency_symbol,
            ),
        )


    with col2:

        st.metric(
            "Balance Due",
            format_currency(
                balance,
                currency_symbol,
            ),
        )


    st.markdown("---")


    notes = st.text_area(
        "Invoice Notes",
        placeholder=(
            "Additional notes for the customer..."
        ),
    )


    st.markdown("---")


    # ========================================================
    # CUSTOMER REMINDER
    # ========================================================

    st.subheader(
        "🔔 Customer Reminder"
    )


    if balance > 0:

        reminder_message = (
            f"Dear {customer_name or 'Customer'},\n\n"
            f"This is a friendly reminder that invoice "
            f"{invoice_number} has an outstanding balance "
            f"of {format_currency(balance, currency_symbol)}."
        )

    else:

        reminder_message = (
            f"Dear {customer_name or 'Customer'},\n\n"
            f"Thank you for settling invoice "
            f"{invoice_number}."
        )


    st.text_area(
        "Suggested Reminder",
        value=reminder_message,
        height=120,
    )


    st.markdown("---")


    # ========================================================
    # GENERATE PDF
    # ========================================================

    if st.button(
        "📄 Generate PDF Invoice",
        type="primary",
        use_container_width=True,
    ):

        if not customer_name.strip():

            st.error(
                "Please enter the customer name."
            )

        elif not items:

            st.error(
                "Please add at least one valid invoice item."
            )

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
                    currency_symbol=currency_symbol,
                )

                st.session_state[
                    "generated_pdf"
                ] = pdf_bytes

                st.session_state[
                    "generated_pdf_currency"
                ] = currency_code

                st.success(
                    "PDF invoice generated successfully."
                )

            except Exception as error:

                st.session_state[
                    "generated_pdf"
                ] = None

                st.error(
                    f"PDF generation failed: "
                    f"{type(error).__name__}: {error}"
                )


    if st.session_state[
        "generated_pdf"
    ]:

        generated_pdf_currency = (
            st.session_state.get(
                "generated_pdf_currency",
                currency_code,
            )
        )

        if generated_pdf_currency != currency_code:

            st.warning(
                "The generated PDF uses a different currency. "
                "Please generate the PDF again for the currently selected currency."
            )

        else:

            st.download_button(
                label="⬇️ Download PDF Invoice",
                data=st.session_state[
                    "generated_pdf"
                ],
                file_name=f"{invoice_number}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )


    st.markdown("---")


    # ========================================================
    # SAVE INVOICE
    # ========================================================

    if st.button(
        "💾 Save Invoice to Database",
        use_container_width=True,
    ):

        if not customer_name.strip():

            st.error(
                "Please enter the customer name."
            )

        elif not items:

            st.error(
                "Please add at least one valid invoice item."
            )

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
                    currency_code=currency_code,
                )

                st.success(
                    f"Invoice saved successfully in {currency_code}."
                )

            except Exception as error:

                st.error(
                    f"Could not save invoice: "
                    f"{type(error).__name__}: {error}"
                )


    st.markdown("---")


    # ========================================================
    # EMAIL INVOICE
    # ========================================================

    if st.button(
        "📧 Send Invoice by Email",
        use_container_width=True,
    ):

        # IMPORTANT:
        # Get the Gmail settings directly from session state.
        sender_email = st.session_state.get(
            "gmail_sender",
            "",
        ).strip()

        sender_password = st.session_state.get(
            "gmail_app_password",
            "",
        ).strip()

        recipient_email = customer_email.strip()


        if not st.session_state[
            "generated_pdf"
        ]:

            st.error(
                "Generate the PDF invoice first."
            )

        elif not recipient_email:

            st.error(
                "Please enter the customer's email address "
                "in the Customer Information section."
            )

        elif not sender_email:

            st.error(
                "Please enter YOUR Gmail address in the sidebar "
                "under Gmail Settings."
            )

        elif not sender_password:

            st.error(
                "Please enter YOUR Gmail App Password in the sidebar "
                "under Gmail Settings."
            )

        elif (
            st.session_state.get(
                "generated_pdf_currency",
                currency_code,
            )
            != currency_code
        ):

            st.error(
                "The PDF was generated using a different currency. "
                "Please generate the PDF again before sending it."
            )

        else:

            try:

                send_invoice_email(
                    sender_email=sender_email,
                    app_password=sender_password,
                    recipient_email=recipient_email,
                    invoice_number=invoice_number,
                    pdf_bytes=st.session_state[
                        "generated_pdf"
                    ],
                    customer_name=customer_name,
                )

                st.success(
                    f"Invoice successfully sent to {recipient_email}."
                )

            except Exception as error:

                st.error(
                    f"Email sending failed: "
                    f"{type(error).__name__}: {error}"
                )


# ============================================================
# INVOICE HISTORY TAB
# ============================================================

with tab2:

    st.subheader(
        "📚 Invoice History"
    )

    try:

        history_df = get_invoice_history()

        if history_df.empty:

            st.info(
                "No invoices have been saved yet."
            )

        else:

            display_df = history_df.copy()

            display_df["currency_code"] = (
                display_df["currency_code"]
                .fillna("NGN")
                .replace("", "NGN")
            )

            display_df["Currency"] = display_df[
                "currency_code"
            ].apply(
                lambda code:
                f"{code} ({get_currency_symbol(code)})"
            )

            display_df["Total"] = display_df.apply(
                lambda row:
                format_currency(
                    row["total_amount"],
                    get_currency_symbol(
                        row["currency_code"]
                    ),
                ),
                axis=1,
            )

            display_df["Amount Paid"] = display_df.apply(
                lambda row:
                format_currency(
                    row["amount_paid"],
                    get_currency_symbol(
                        row["currency_code"]
                    ),
                ),
                axis=1,
            )

            display_df["Balance"] = display_df.apply(
                lambda row:
                format_currency(
                    row["balance"],
                    get_currency_symbol(
                        row["currency_code"]
                    ),
                ),
                axis=1,
            )

            history_columns = [
                "invoice_number",
                "customer_name",
                "customer_email",
                "invoice_date",
                "Currency",
                "Total",
                "Amount Paid",
                "Balance",
                "status",
            ]

            available_columns = [
                column
                for column in history_columns
                if column in display_df.columns
            ]

            display_df = display_df[
                available_columns
            ]

            display_df = display_df.rename(
                columns={
                    "invoice_number": "Invoice Number",
                    "customer_name": "Customer Name",
                    "customer_email": "Customer Email",
                    "invoice_date": "Invoice Date",
                    "status": "Status",
                }
            )

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
            )

    except Exception as error:

        st.error(
            f"Could not load invoice history: "
            f"{type(error).__name__}: {error}"
        )


# ============================================================
# ANALYTICS TAB
# ============================================================

with tab3:

    st.subheader(
        "📊 Analytics Dashboard"
    )

    try:

        analytics_df = get_invoice_history()

        if analytics_df.empty:

            st.info(
                "Save some invoices first to see analytics."
            )

        else:

            analytics_df[
                "currency_code"
            ] = analytics_df[
                "currency_code"
            ].fillna("NGN")

            available_codes = (
                analytics_df[
                    "currency_code"
                ]
                .unique()
                .tolist()
            )

            available_currency_options = []

            for code in available_codes:

                symbol = get_currency_symbol(
                    code
                )

                available_currency_options.append(
                    f"{code} ({symbol})"
                )

            selected_analytics_currency = st.selectbox(
                "💱 Analytics Currency",
                available_currency_options,
            )

            selected_analytics_code = (
                selected_analytics_currency
                .split(" ")[0]
            )

            analytics_symbol = get_currency_symbol(
                selected_analytics_code
            )

            currency_analytics_df = (
                analytics_df[
                    analytics_df[
                        "currency_code"
                    ]
                    == selected_analytics_code
                ]
                .copy()
            )

            if currency_analytics_df.empty:

                st.info(
                    "No invoices are available "
                    "for this currency."
                )

            else:

                total_invoiced = (
                    pd.to_numeric(
                        currency_analytics_df[
                            "total_amount"
                        ],
                        errors="coerce",
                    )
                    .fillna(0)
                    .sum()
                )

                total_collected = (
                    pd.to_numeric(
                        currency_analytics_df[
                            "amount_paid"
                        ],
                        errors="coerce",
                    )
                    .fillna(0)
                    .sum()
                )

                total_debt = (
                    pd.to_numeric(
                        currency_analytics_df[
                            "balance"
                        ],
                        errors="coerce",
                    )
                    .fillna(0)
                    .sum()
                )

                invoice_count = len(
                    currency_analytics_df
                )

                st.info(
                    f"Analytics are showing "
                    f"{selected_analytics_code} "
                    f"({analytics_symbol}) invoices only."
                )

                col1, col2, col3, col4 = st.columns(4)

                with col1:

                    st.metric(
                        "Total Invoiced",
                        format_currency(
                            total_invoiced,
                            analytics_symbol,
                        ),
                    )

                with col2:

                    st.metric(
                        "Total Collected",
                        format_currency(
                            total_collected,
                            analytics_symbol,
                        ),
                    )

                with col3:

                    st.metric(
                        "Outstanding Debt",
                        format_currency(
                            total_debt,
                            analytics_symbol,
                        ),
                    )

                with col4:

                    st.metric(
                        "Number of Invoices",
                        invoice_count,
                    )

                st.markdown("---")

                chart_data = pd.DataFrame(
                    {
                        "Category": [
                            "Collected",
                            "Outstanding",
                        ],
                        "Amount": [
                            total_collected,
                            total_debt,
                        ],
                    }
                )

                fig_pie = px.pie(
                    chart_data,
                    names="Category",
                    values="Amount",
                    title=(
                        f"Collected vs Outstanding "
                        f"({selected_analytics_code})"
                    ),
                )

                st.plotly_chart(
                    fig_pie,
                    use_container_width=True,
                )

                status_data = (
                    currency_analytics_df[
                        "status"
                    ]
                    .value_counts()
                    .reset_index()
                )

                status_data.columns = [
                    "Status",
                    "Count",
                ]

                fig_bar = px.bar(
                    status_data,
                    x="Status",
                    y="Count",
                    title=(
                        f"Invoice Status "
                        f"({selected_analytics_code})"
                    ),
                )

                st.plotly_chart(
                    fig_bar,
                    use_container_width=True,
                )

    except Exception as error:

        st.error(
            f"Analytics error: "
            f"{type(error).__name__}: {error}"
        )


# ============================================================
# CUSTOMER FOLLOW-UP
# ============================================================

st.markdown("---")

st.header(
    "📞 Customer Follow-Up"
)


try:

    followup_df = get_invoice_history()

    if followup_df.empty:

        st.info(
            "There are no saved invoices requiring follow-up."
        )

    else:

        followup_df[
            "currency_code"
        ] = followup_df[
            "currency_code"
        ].fillna("NGN")

        followup_df[
            "balance"
        ] = pd.to_numeric(
            followup_df["balance"],
            errors="coerce",
        ).fillna(0.0)

        debt_df = followup_df[
            followup_df["balance"] > 0
        ].copy()

        if debt_df.empty:

            st.success(
                "No outstanding customer debts."
            )

        else:

            st.warning(
                f"{len(debt_df)} invoice(s) "
                "have outstanding balances."
            )

            for _, row in debt_df.iterrows():

                row_currency_code = row.get(
                    "currency_code",
                    "NGN",
                )

                row_currency_symbol = (
                    get_currency_symbol(
                        row_currency_code
                    )
                )

                balance_display = format_currency(
                    row["balance"],
                    row_currency_symbol,
                )

                st.write(
                    f"**{row['customer_name']}** — "
                    f"Invoice {row['invoice_number']} — "
                    f"Balance: {balance_display} "
                    f"({row_currency_code})"
                )


except Exception as error:

    st.error(
        f"Follow-up section error: "
        f"{type(error).__name__}: {error}"
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "Smart Invoicer & Debt Collector"
)
