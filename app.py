
import streamlit as st
import database

from ai_engine import (
    analyze_civic_image,
    compare_repair_images,
    civic_assistant_reply
)

from streamlit_geolocation import streamlit_geolocation

from pathlib import Path
from datetime import datetime
from html import escape
import sqlite3
import json

import pandas as pd
import plotly.express as px
import folium
from streamlit_folium import st_folium


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="CIVIC EYE | Smart City Reporting",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# CONSTANTS
# ==========================================

DB_PATH = Path("database/civic_eye.db")

STATUSES = [
    "Submitted",
    "Under Review",
    "Assigned",
    "In Progress",
    "Resolved",
    "Rejected"
]

DEPARTMENTS = [
    "Roads and Infrastructure Department",
    "Sanitation and Waste Management Department",
    "Water Supply Department",
    "Drainage and Sewerage Department",
    "Streetlight and Electrical Department",
    "Public Health Department",
    "Other Department"
]


# ==========================================
# REPAIR VERIFICATION DATABASE FUNCTIONS
# ==========================================

def save_repair_evidence(complaint_id, image_path, analysis):

    with sqlite3.connect(DB_PATH) as con:

        cursor = con.execute("""
            UPDATE complaints
            SET repair_image_path = ?,
                repair_analysis = ?,
                repair_uploaded_at = ?,
                repair_verified = 0
            WHERE complaint_id = ?
        """, (
            str(image_path),
            json.dumps(analysis),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            complaint_id
        ))

        return cursor.rowcount > 0


def confirm_repair_resolution(complaint_id):

    with sqlite3.connect(DB_PATH) as con:

        cursor = con.execute("""
            UPDATE complaints
            SET repair_verified = 1,
                status = 'Resolved'
            WHERE complaint_id = ?
              AND repair_image_path IS NOT NULL
              AND repair_analysis IS NOT NULL
        """, (complaint_id,))

        return cursor.rowcount > 0


def reject_repair_resolution(complaint_id):

    with sqlite3.connect(DB_PATH) as con:

        cursor = con.execute("""
            UPDATE complaints
            SET repair_verified = 0,
                status = 'In Progress'
            WHERE complaint_id = ?
        """, (complaint_id,))

        return cursor.rowcount > 0


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def save_complaint(payload):

    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)

    extension = Path(payload["image_name"]).suffix.lower()

    if extension not in [".jpg", ".jpeg", ".png"]:
        extension = ".jpg"

    image_path = (
        upload_dir /
        f"report_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
    )

    image_path.write_bytes(payload["image_bytes"])

    complaint_id = database.add_complaint(
        citizen_name=payload["citizen_name"],
        issue_type=payload["issue_type"],
        description=payload["description"],
        location=payload["location"],
        severity=payload["severity"],
        department=payload["department"],
        urgency=payload["urgency"],
        confidence=payload["confidence"],
        image_path=str(image_path),
        latitude=payload["latitude"],
        longitude=payload["longitude"]
    )

    return complaint_id


def clear_report_state():

    keys = [
        "ai_result",
        "image_bytes",
        "image_name",
        "gps_latitude",
        "gps_longitude",
        "last_auto_gps",
        "pending_complaint",
        "possible_duplicates"
    ]

    for key in keys:
        st.session_state.pop(key, None)


def complete_submission(payload):

    try:

        complaint_id = save_complaint(payload)

        clear_report_state()

        st.session_state["submitted_id"] = complaint_id

        st.rerun()

    except Exception as error:

        st.error(f"Could not save complaint: {error}")


def save_repair_image(uploaded_file, complaint_id):

    upload_dir = Path("uploads/repairs")
    upload_dir.mkdir(parents=True, exist_ok=True)

    extension = Path(uploaded_file.name).suffix.lower()

    if extension not in [".jpg", ".jpeg", ".png"]:
        raise ValueError("Only JPG, JPEG and PNG images are allowed.")

    filename = (
        f"repair_{complaint_id}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        f"{extension}"
    )

    image_path = upload_dir / filename
    image_path.write_bytes(uploaded_file.getvalue())

    return image_path


def display_civic_map(dataframe):

    st.subheader("🗺️ Live Civic Complaint Map")

    st.write(
        "Explore reported civic problems using their stored GPS coordinates."
    )

    map_df = dataframe.copy()

    map_df["latitude"] = pd.to_numeric(
        map_df["latitude"], errors="coerce"
    )

    map_df["longitude"] = pd.to_numeric(
        map_df["longitude"], errors="coerce"
    )

    map_df = map_df.dropna(
        subset=["latitude", "longitude"]
    ).copy()

    map_df = map_df[
        map_df["latitude"].between(-90, 90)
        & map_df["longitude"].between(-180, 180)
    ]

    total_reports = len(dataframe)
    mapped_reports = len(map_df)

    col1, col2 = st.columns(2)

    col1.metric("Reports with GPS Coordinates", mapped_reports)

    col2.metric(
        "Reports without GPS Coordinates",
        total_reports - mapped_reports
    )

    st.divider()

    if map_df.empty:

        st.info(
            "No complaints have valid GPS coordinates yet. "
            "Submit a report with GPS coordinates to display it on the map."
        )

        return

    severity_colors = {
        "Critical": "red",
        "High": "orange",
        "Medium": "blue",
        "Low": "green"
    }

    center_lat = map_df["latitude"].mean()
    center_lon = map_df["longitude"].mean()

    civic_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="OpenStreetMap",
        control_scale=True
    )

    coordinates = []

    for _, complaint in map_df.iterrows():

        lat = float(complaint["latitude"])
        lon = float(complaint["longitude"])

        coordinates.append([lat, lon])

        severity = str(
            complaint.get("severity") or "Unknown"
        )

        marker_color = severity_colors.get(severity, "gray")

        complaint_id = escape(
            str(complaint.get("complaint_id", "Unknown"))
        )

        issue = escape(
            str(complaint.get("issue_type", "Unknown"))
        )

        location = escape(
            str(complaint.get("location", "Unknown"))
        )

        status = escape(
            str(complaint.get("status", "Unknown"))
        )

        description = escape(
            str(complaint.get("description", ""))
        )

        popup_html = f"""
        <div style="width:250px; font-family:Arial;">
            <h3 style="color:#0878c9;">CIVIC EYE Report</h3>
            <b>Complaint ID:</b> {complaint_id}<br>
            <b>Issue:</b> {issue}<br>
            <b>Location:</b> {location}<br>
            <b>Severity:</b> {escape(severity)}<br>
            <b>Status:</b> {status}<br>
            <b>Coordinates:</b> {lat:.6f}, {lon:.6f}<br>
            <hr>
            <b>Description:</b><br>
            {description}
        </div>
        """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=f"{issue} | {complaint_id}",
            icon=folium.Icon(
                color=marker_color,
                icon="info-sign"
            )
        ).add_to(civic_map)

    if len(coordinates) > 1:
        civic_map.fit_bounds(coordinates)

    st_folium(
        civic_map,
        width=1200,
        height=550,
        returned_objects=[]
    )

    st.markdown("### Marker Colour Guide")

    col1, col2, col3, col4 = st.columns(4)

    col1.markdown("🔴 **Critical**")
    col2.markdown("🟠 **High**")
    col3.markdown("🔵 **Medium**")
    col4.markdown("🟢 **Low**")

    st.caption(
        "GPS coordinates are user-provided and "
        "are not independently verified."
    )


# ==========================================
# CUSTOM STYLING
# ==========================================

st.markdown("""
<style>
/* CIVIC EYE premium civic-tech theme */
:root {
    --ce-bg: #0b1220;
    --ce-panel: #111c2e;
    --ce-panel-2: #17243a;
    --ce-border: rgba(148, 163, 184, .16);
    --ce-blue: #3b82f6;
    --ce-cyan: #22d3ee;
    --ce-text: #e7eef8;
    --ce-muted: #9aaec5;
}
.stApp { background: radial-gradient(ellipse at top left, #14243b 0%, #0b1220 42%, #090f19 100%); color: var(--ce-text); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { right: 1rem; }
.block-container { padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 1500px; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #0d1727 0%, #101b2b 100%); border-right: 1px solid var(--ce-border); }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #b8c8dc; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #f4f8ff; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: .3rem; }
[data-testid="stSidebar"] [role="radiogroup"] label { border-radius: 10px; padding: .48rem .55rem; transition: background .18s ease; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(59,130,246,.12); }
[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"] { background: rgba(59,130,246,.18); border: 1px solid rgba(59,130,246,.35); }
.hero { background: linear-gradient(120deg, #10233b 0%, #123b63 55%, #155e75 100%); border: 1px solid rgba(96, 165, 250, .22); padding: 2.15rem 2.3rem; border-radius: 22px; color: white; margin-bottom: 1.7rem; box-shadow: 0 18px 45px rgba(0,0,0,.22); position: relative; overflow: hidden; }
.hero:after { content: ""; position: absolute; width: 240px; height: 240px; border-radius: 50%; background: rgba(34,211,238,.09); right: -70px; top: -80px; }
.hero h1 { color: white !important; font-size: clamp(2rem, 3vw, 3rem) !important; font-weight: 800 !important; letter-spacing: -.04em; margin-bottom: .3rem; }
.hero p { color: #d5e9ff !important; font-size: 1.04rem; margin-bottom: .35rem; }
.hero .hero-tag { color: #8ee9ff; font-size: .8rem; font-weight: 700; text-transform: uppercase; letter-spacing: .14em; }
h1, h2, h3 { letter-spacing: -.025em; color: #f1f6ff; }
h2 { margin-top: .4rem !important; }
[data-testid="stMetric"] { background: linear-gradient(145deg, #142238, #101a2b); border: 1px solid var(--ce-border); padding: 1rem 1.1rem; border-radius: 16px; box-shadow: 0 6px 18px rgba(0,0,0,.12); }
[data-testid="stMetricLabel"] { color: #a9bfd9 !important; font-size: .9rem; }
[data-testid="stMetricValue"] { color: #f4f8ff !important; font-weight: 750; }
[data-testid="stMetricDelta"] { color: var(--ce-cyan) !important; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--ce-border) !important; border-radius: 15px !important; background: rgba(17,28,46,.35); }
[data-testid="stExpander"] { border: 1px solid var(--ce-border); border-radius: 13px; background: rgba(17,28,46,.35); }
[data-testid="stTabs"] button { color: var(--ce-muted); }
[data-testid="stAlert"] { border-radius: 12px; }
[data-testid="stDataFrame"] { border: 1px solid var(--ce-border); border-radius: 12px; overflow: hidden; }
[data-testid="stFileUploader"] { border: 1px dashed rgba(96,165,250,.45); border-radius: 14px; background: rgba(30,58,91,.18); padding: .4rem; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stSelectbox"] div[data-baseweb="select"] { border-radius: 10px !important; }
[data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button { border-radius: 10px; border: 1px solid rgba(96,165,250,.25); font-weight: 650; transition: all .15s ease; }
[data-testid="stButton"] button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] { background: linear-gradient(110deg, #2563eb, #0891b2); color: white; border: 0; }
[data-testid="stButton"] button:hover, [data-testid="stFormSubmitButton"] button:hover { border-color: #38bdf8; transform: translateY(-1px); }
hr { border-color: rgba(148,163,184,.16) !important; }
small, [data-testid="stCaptionContainer"] { color: #91a7c1 !important; }
footer { visibility: hidden; }
@media (max-width: 768px) { .block-container { padding: 1rem .8rem 2rem; } .hero { padding: 1.35rem; border-radius: 16px; } }
</style>
""", unsafe_allow_html=True);

# ==========================================
# HEADER
# ==========================================

st.markdown("""
<div class="hero">
    <div class="hero-tag">Smart City · AI · Citizen-first</div>
    <h1>🏙️ CIVIC EYE</h1>
    <p>AI-powered civic problem detection and accountability platform</p>
    <p><b>Report problems. Track progress. Build better cities.</b></p>
</div>
""", unsafe_allow_html=True)

# ==========================================
# SIDEBAR
# ==========================================

st.sidebar.markdown("# 🏙️ CIVIC EYE")
st.sidebar.caption("CITIZEN-POWERED SMART CITY PLATFORM")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    [
        "Home Dashboard",
        "Public Analytics Dashboard",
        "Report a Problem",
        "Track Complaint",
        "Multilingual Civic Assistant",
        "Admin Dashboard"
    ],
    key="civic_eye_navigation"
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Citizen access**")
st.sidebar.caption("No citizen login or registration required.")
st.sidebar.caption("Prototype · AI estimates require human review")

# ==========================================
# LOAD COMPLAINT DATA
# ==========================================

complaints = database.get_all_complaints()


# ==========================================
# HOME DASHBOARD
# ==========================================

if page == "Home Dashboard":

    st.title("🏙️ City Overview")

    st.write("Welcome to the CIVIC EYE citizen platform.")

    total = len(complaints)

    resolved = sum(
        c["status"] == "Resolved"
        for c in complaints
    )

    pending = total - resolved

    high_severity = sum(
        c["severity"] in ["High", "Critical"]
        for c in complaints
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Complaints", total)
    col2.metric("Resolved", resolved)
    col3.metric("Not Yet Resolved", pending)
    col4.metric("High/Critical Severity", high_severity)

    st.divider()

    st.subheader("Recent Civic Reports")

    if complaints:

        recent_data = [
            {
                "Complaint ID": c["complaint_id"],
                "Issue": c["issue_type"],
                "Location": c["location"],
                "Severity": c["severity"],
                "Status": c["status"]
            }
            for c in complaints[:10]
        ]

        st.dataframe(
            recent_data,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info("No complaints have been submitted yet.")

    st.caption(
        "CIVIC EYE MVP: Reports are stored locally "
        "for demonstration and admin review."
    )


# ==========================================
# PUBLIC ANALYTICS DASHBOARD
# ==========================================

elif page == "Public Analytics Dashboard":

    st.title("📊 Public Civic Analytics")

    st.write(
        "Explore complaint trends, severity levels, "
        "and resolution progress."
    )

    if not complaints:

        st.info("No complaint data is available yet.")

    else:

        df = pd.DataFrame(complaints)

        total = len(df)

        resolved = int(
            (df["status"] == "Resolved").sum()
        )

        pending = total - resolved

        resolution_rate = (
            resolved / total * 100
            if total > 0 else 0
        )

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Total Reports", total)
        col2.metric("Resolved Reports", resolved)
        col3.metric("Pending Reports", pending)

        col4.metric(
            "Resolution Rate",
            f"{resolution_rate:.1f}%"
        )

        st.divider()

        st.subheader("🚨 Severity Overview")

        severity_counts = (
            df["severity"]
            .fillna("Unknown")
            .value_counts()
            .reset_index()
        )

        severity_counts.columns = ["Severity", "Reports"]

        col1, col2 = st.columns(2)

        with col1:

            severity_chart = px.bar(
                severity_counts,
                x="Severity",
                y="Reports",
                color="Severity",
                title="Reports by Severity",
                text="Reports"
            )

            severity_chart.update_layout(showlegend=False)

            st.plotly_chart(
                severity_chart,
                use_container_width=True
            )

        with col2:

            status_counts = (
                df["status"]
                .fillna("Unknown")
                .value_counts()
                .reset_index()
            )

            status_counts.columns = ["Status", "Reports"]

            status_chart = px.pie(
                status_counts,
                names="Status",
                values="Reports",
                title="Complaint Status Distribution",
                hole=0.4
            )

            st.plotly_chart(
                status_chart,
                use_container_width=True
            )

        st.divider()

        st.subheader("📌 Civic Issue Categories")

        issue_counts = (
            df["issue_type"]
            .fillna("Unknown")
            .value_counts()
            .reset_index()
        )

        issue_counts.columns = ["Issue Type", "Reports"]

        issue_chart = px.bar(
            issue_counts,
            x="Issue Type",
            y="Reports",
            color="Issue Type",
            title="Number of Reports by Issue Category",
            text="Reports"
        )

        issue_chart.update_layout(showlegend=False)

        st.plotly_chart(
            issue_chart,
            use_container_width=True
        )

        st.divider()

        st.subheader("📍 Location-wise Reports")

        location_counts = (
            df["location"]
            .fillna("Unknown")
            .value_counts()
            .reset_index()
        )

        location_counts.columns = ["Location", "Reports"]

        location_chart = px.bar(
            location_counts,
            x="Location",
            y="Reports",
            color="Reports",
            title="Civic Problems by Reported Location",
            text="Reports"
        )

        st.plotly_chart(
            location_chart,
            use_container_width=True
        )

        st.divider()

        display_civic_map(df)

        st.divider()

        st.subheader("📋 Recent Public Reports")

        public_data = df[
            [
                "complaint_id",
            "issue_type",
            "location",
            "severity",
            "status",
            "created_at"
            ]
        ].head(10).copy()

        public_data.columns = [
            "Complaint ID",
            "Issue",
            "Location",
            "Severity",
            "Status",
            "Submitted At"
        ]

        st.dataframe(
            public_data,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            "Analytics are based on reports stored in this "
            "CIVIC EYE demonstration database. "
            "They do not represent official municipal statistics."
        )


# ==========================================
# REPORT A PROBLEM
# ==========================================

elif page == "Report a Problem":

    st.title("📸 Report a Civic Problem")

    st.write(
        "Upload a photograph. Our AI will analyze "
        "the visible civic issue."
    )

    uploaded_file = st.file_uploader(
        "Upload a problem photograph",
        type=["jpg", "jpeg", "png"],
        key="citizen_image_upload"
    )

    if uploaded_file is not None:

        image_bytes = uploaded_file.getvalue()

        st.image(
            image_bytes,
            caption="Uploaded Civic Problem",
            use_container_width=True
        )

        if st.button("🤖 Analyze Image with AI"):

            with st.spinner("Gemini AI is analyzing your image..."):

                result = analyze_civic_image(
                    image_bytes,
                    uploaded_file.type
                )

                st.session_state["ai_result"] = result
                st.session_state["image_bytes"] = image_bytes
                st.session_state["image_name"] = uploaded_file.name

    result = st.session_state.get("ai_result")

    if uploaded_file is not None:

        if st.session_state.get("image_bytes") != uploaded_file.getvalue():
            result = None

    else:

        result = None

    if result:

        if result["success"]:

            analysis = result["analysis"]

            st.success("AI image analysis completed!")

            st.subheader("AI Analysis Results")

            col1, col2 = st.columns(2)

            col1.metric(
                "Detected Issue",
                analysis.get("issue_type", "Unknown")
            )

            col2.metric(
                "Severity Estimate",
                analysis.get("severity", "Unknown")
            )

            st.write("**Description:**", analysis.get("description", ""))

            st.write(
                "**Suggested Department:**",
                analysis.get("department", "")
            )

            st.write("**Urgency Estimate:**", analysis.get("urgency", ""))

            st.write("**AI Confidence:**", analysis.get("confidence", ""))

            st.warning(
                "AI severity and confidence are estimates, "
                "not official municipal decisions. "
                "Please review the result before submitting."
            )

            st.divider()

            st.subheader("📍 Automatic GPS Detection")

            st.caption(
                "Click the location button and allow your browser "
                "to access your location. You can also enter "
                "coordinates manually below."
            )

            if "gps_latitude" not in st.session_state:
                st.session_state["gps_latitude"] = ""

            if "gps_longitude" not in st.session_state:
                st.session_state["gps_longitude"] = ""

            gps_location = streamlit_geolocation()

            if isinstance(gps_location, dict):

                detected_lat = gps_location.get("latitude")
                detected_lon = gps_location.get("longitude")

                if detected_lat is not None and detected_lon is not None:

                    try:

                        detected_lat = float(detected_lat)
                        detected_lon = float(detected_lon)

                        if not (
                            -90 <= detected_lat <= 90
                            and -180 <= detected_lon <= 180
                        ):
                            raise ValueError("Invalid GPS coordinates.")

                        gps_pair = (detected_lat, detected_lon)

                        if st.session_state.get("last_auto_gps") != gps_pair:

                            st.session_state["gps_latitude"] = str(detected_lat)
                            st.session_state["gps_longitude"] = str(detected_lon)

                            st.session_state["last_auto_gps"] = gps_pair

                        st.success("GPS location detected successfully!")

                        gps_col1, gps_col2 = st.columns(2)

                        gps_col1.metric(
                            "Detected Latitude",
                            f"{detected_lat:.6f}"
                        )

                        gps_col2.metric(
                            "Detected Longitude",
                            f"{detected_lon:.6f}"
                        )

                        accuracy = gps_location.get("accuracy")

                        if accuracy is not None:

                            st.caption(
                                f"Estimated GPS accuracy: {float(accuracy):.1f} metres"
                            )

                    except (TypeError, ValueError) as error:

                        st.error(f"Could not use GPS coordinates: {error}")

            st.divider()

            st.subheader("👤 Citizen Details")

            with st.form("complaint_form"):

                citizen_name = st.text_input("Your Name")

                location = st.text_input(
                    "Problem Location",
                    placeholder="Example: Baner, Pune"
                )

                st.markdown("### 📍 GPS Coordinates")

                latitude = st.text_input(
                    "Latitude",
                    placeholder="Automatically detected or enter manually",
                    key="gps_latitude"
                )

                longitude = st.text_input(
                    "Longitude",
                    placeholder="Automatically detected or enter manually",
                    key="gps_longitude"
                )

                extra_description = st.text_area(
                    "Additional Details (Optional)"
                )

                submitted = st.form_submit_button(
                    "Submit Civic Complaint"
                )

            if submitted:

                if not citizen_name.strip():

                    st.error("Please enter your name.")

                elif not location.strip():

                    st.error("Please enter the problem location.")

                elif bool(latitude.strip()) != bool(longitude.strip()):

                    st.error(
                        "Please enter both latitude and longitude, "
                        "or leave both empty."
                    )

                else:

                    try:

                        latitude_value = (
                            float(latitude.strip())
                            if latitude.strip() else None
                        )

                        longitude_value = (
                            float(longitude.strip())
                            if longitude.strip() else None
                        )

                        if latitude_value is not None:

                            if not -90 <= latitude_value <= 90:
                                raise ValueError(
                                    "Latitude must be between -90 and 90."
                                )

                            if not -180 <= longitude_value <= 180:
                                raise ValueError(
                                    "Longitude must be between -180 and 180."
                                )

                        description = analysis.get("description", "")

                        if extra_description.strip():

                            description += (
                                " Citizen details: "
                                + extra_description.strip()
                            )

                        pending_payload = {
                            "citizen_name": citizen_name.strip(),
                            "issue_type": analysis.get("issue_type", "Unknown"),
                            "description": description,
                            "location": location.strip(),
                            "severity": analysis.get("severity"),
                            "department": analysis.get("department"),
                            "urgency": analysis.get("urgency"),
                            "confidence": analysis.get("confidence"),
                            "image_bytes": st.session_state["image_bytes"],
                            "image_name": st.session_state["image_name"],
                            "latitude": latitude_value,
                            "longitude": longitude_value
                        }

                        with st.spinner("Checking for possible duplicate complaints..."):

                            duplicates = database.find_possible_duplicates(
                                issue_type=pending_payload["issue_type"],
                                description=pending_payload["description"],
                                location=pending_payload["location"],
                                latitude=latitude_value,
                                longitude=longitude_value
                            )

                        if duplicates:

                            st.session_state["pending_complaint"] = pending_payload
                            st.session_state["possible_duplicates"] = duplicates

                        else:

                            complete_submission(pending_payload)

                    except ValueError as error:

                        st.error(f"Invalid input: {error}")

                    except Exception as error:

                        st.error(f"Duplicate detection failed: {error}")

            pending_payload = st.session_state.get("pending_complaint")

            duplicates = st.session_state.get("possible_duplicates", [])

            if pending_payload and duplicates:

                st.divider()

                st.error("⚠️ Possible duplicate complaints detected!")

                st.write(
                    "CIVIC EYE found existing reports that may describe "
                    "the same civic problem."
                )

                for duplicate in duplicates:

                    with st.container(border=True):

                        st.markdown(
                            f"**Complaint ID:** {duplicate['complaint_id']}"
                        )

                        st.write("**Issue:**", duplicate["issue_type"])
                        st.write("**Location:**", duplicate["location"])
                        st.write("**Status:**", duplicate["status"])
                        st.write("**Description:**", duplicate["description"])

                        st.write(
                            "**Description similarity:**",
                            f"{duplicate['similarity']}%"
                        )

                        if duplicate["distance_m"] is not None:

                            st.write(
                                "**GPS distance:**",
                                f"{duplicate['distance_m']} metres"
                            )

                st.warning(
                    "These are possible matches, not confirmed duplicates. "
                    "You can still submit your report."
                )

                confirm_col1, confirm_col2 = st.columns(2)

                with confirm_col1:

                    if st.button(
                        "Submit Anyway",
                        type="primary",
                        use_container_width=True,
                        key="confirm_duplicate_submit"
                    ):

                        complete_submission(pending_payload)

                with confirm_col2:

                    if st.button(
                        "Cancel Submission",
                        use_container_width=True,
                        key="cancel_duplicate_submit"
                    ):

                        st.session_state.pop("pending_complaint", None)
                        st.session_state.pop("possible_duplicates", None)

                        st.info("Submission cancelled.")

        else:

            st.error("AI analysis failed: " + str(result["error"]))

            st.info("Please try again later or use another image.")

    if st.session_state.get("submitted_id"):

        st.success("Your complaint was submitted successfully!")

        st.title(st.session_state["submitted_id"])

        st.write("Save this complaint ID to track your report.")

        if st.button("Clear Confirmation"):

            st.session_state.pop("submitted_id", None)

            st.rerun()


# ==========================================
# TRACK COMPLAINT
# ==========================================

elif page == "Track Complaint":

    st.title("🔍 Track Your Complaint")

    complaint_id = st.text_input(
        "Enter your Complaint ID",
        placeholder="Example: CE-CE55AF4B"
    )

    if st.button("Track Complaint"):

        if complaint_id.strip():

            complaint = database.get_complaint(
                complaint_id.strip().upper()
            )

            if complaint:

                st.success("Complaint found!")

                st.subheader(complaint["complaint_id"])

                st.write("**Issue:**", complaint["issue_type"])
                st.write("**Location:**", complaint["location"])
                st.write("**Severity:**", complaint["severity"])
                st.write("**Suggested Department:**", complaint["department"])

                st.write(
                    "**Assigned Department:**",
                    complaint.get("assigned_department") or "Not assigned yet"
                )

                st.write("**Status:**", complaint["status"])
                st.write("**Submitted:**", complaint["created_at"])

                if complaint.get("repair_uploaded_at"):

                    st.write(
                        "**Repair Evidence Uploaded:**",
                        complaint["repair_uploaded_at"]
                    )

                    if complaint.get("repair_verified") == 1:

                        st.success("Admin has confirmed repair resolution.")

                    else:

                        st.info("Repair evidence is awaiting admin verification.")

                if (
                    complaint.get("latitude") is not None
                    and complaint.get("longitude") is not None
                ):

                    st.write(
                        "**Coordinates:**",
                        complaint["latitude"],
                        complaint["longitude"]
                    )

            else:

                st.error("Complaint ID not found.")

        else:

            st.warning("Please enter a complaint ID.")


# ==========================================
# MULTILINGUAL CIVIC ASSISTANT
# ==========================================

elif page == "Multilingual Civic Assistant":

    st.title("🌐 Multilingual Civic Assistant")

    st.write(
        "Ask questions about civic issues, complaint reporting, "
        "tracking and repair verification."
    )

    language = st.selectbox(
        "Choose your language",
        ["English", "Hindi", "Marathi"],
        key="civic_assistant_language"
    )

    language_map = {
        "English": "English",
        "Hindi": "Hindi (हिन्दी)",
        "Marathi": "Marathi (मराठी)"
    }

    st.info(
        f"Assistant will respond in {language_map[language]}."
    )

    if "civic_chat_history" not in st.session_state:
        st.session_state["civic_chat_history"] = []

    # DISPLAY PREVIOUS CHAT MESSAGES

    for message in st.session_state["civic_chat_history"]:

        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # CHAT INPUT

    user_question = st.chat_input(
        "Ask about civic problems or complaint tracking..."
    )

    if user_question:

        st.session_state["civic_chat_history"].append({
            "role": "user",
            "content": user_question
        })

        with st.chat_message("user"):
            st.markdown(user_question)

        with st.chat_message("assistant"):

            with st.spinner("CIVIC EYE is thinking..."):

                response = civic_assistant_reply(
                    user_question,
                    language
                )

                if response["success"]:

                    answer = response["answer"]

                    st.markdown(answer)

                    st.session_state["civic_chat_history"].append({
                        "role": "assistant",
                        "content": answer
                    })

                else:

                    st.error(
                        "Assistant error: "
                        + str(response["error"])
                    )

    # CLEAR CHAT

    if st.session_state["civic_chat_history"]:

        if st.button("🗑️ Clear Chat"):

            st.session_state["civic_chat_history"] = []

            st.rerun()


# ==========================================
# ADMIN DASHBOARD
# ==========================================

elif page == "Admin Dashboard":

    st.title("🛡️ CIVIC EYE Admin Dashboard")

    st.warning(
        "Demonstration admin interface. This MVP does not have "
        "production admin authentication or direct municipal integration."
    )

    complaints = database.get_all_complaints()

    if complaints:

        df = pd.DataFrame(complaints)

        total = len(df)

        submitted_count = int(
            (df["status"] == "Submitted").sum()
        )

        assigned_count = int(
            df["assigned_department"].fillna("").ne("").sum()
        )

        in_progress_count = int(
            (df["status"] == "In Progress").sum()
        )

        resolved_count = int(
            (df["status"] == "Resolved").sum()
        )

        col1, col2, col3, col4, col5 = st.columns(5)

        col1.metric("Total Complaints", total)
        col2.metric("New / Submitted", submitted_count)
        col3.metric("Assigned", assigned_count)
        col4.metric("In Progress", in_progress_count)
        col5.metric("Resolved", resolved_count)

        st.divider()

        st.subheader("🔎 Filter Complaints")

        filter_col1, filter_col2 = st.columns(2)

        with filter_col1:

            selected_filter = st.selectbox(
                "Filter by Status",
                ["All"] + STATUSES,
                key="admin_status_filter"
            )

        with filter_col2:

            search_id = st.text_input(
                "Search Complaint ID",
                placeholder="Enter complaint ID",
                key="admin_search_id"
            )

        filtered_complaints = complaints

        if selected_filter != "All":

            filtered_complaints = [
                c for c in filtered_complaints
                if c["status"] == selected_filter
            ]

        if search_id.strip():

            filtered_complaints = [
                c for c in filtered_complaints
                if search_id.strip().upper()
                in c["complaint_id"].upper()
            ]

        st.write(
            f"**Showing {len(filtered_complaints)} complaint(s)**"
        )

        st.divider()

        st.subheader("📋 Complaint Management")

        for complaint in filtered_complaints:

            complaint_id = complaint["complaint_id"]

            current_status = complaint.get("status") or "Submitted"

            current_department = (
                complaint.get("assigned_department") or ""
            )

            verified = complaint.get("repair_verified") == 1

            with st.expander(
                f"{complaint_id} | {complaint['issue_type']} | {current_status}",
                expanded=False
            ):

                # CITIZEN REPORT

                st.markdown("### 📝 Citizen Report")

                detail_col1, detail_col2 = st.columns(2)

                with detail_col1:

                    st.write("**Citizen:**", complaint["citizen_name"])
                    st.write("**Issue:**", complaint["issue_type"])
                    st.write("**Location:**", complaint["location"])
                    st.write("**Severity:**", complaint["severity"])

                with detail_col2:

                    st.write("**Urgency Estimate:**", complaint["urgency"])
                    st.write("**AI Confidence:**", complaint["confidence"])
                    st.write("**Submitted At:**", complaint["created_at"])
                    st.write("**Current Status:**", current_status)

                st.write("**Description:**", complaint["description"])

                image_path = complaint.get("image_path")

                if image_path and Path(image_path).exists():

                    st.image(
                        image_path,
                        caption="Original Citizen Evidence",
                        width=400
                    )

                if (
                    complaint.get("latitude") is not None
                    and complaint.get("longitude") is not None
                ):

                    st.write(
                        "**GPS Coordinates:**",
                        f"{complaint['latitude']}, {complaint['longitude']}"
                    )

                st.divider()

                # DEPARTMENT ASSIGNMENT

                st.markdown("### 🏢 Department Assignment")

                st.write(
                    "**AI Suggested Department:**",
                    complaint.get("department") or "Not available"
                )

                if current_department:

                    st.success(
                        f"Currently assigned to: {current_department}"
                    )

                    st.caption(
                        f"Assigned at: "
                        f"{complaint.get('assigned_at') or 'Date unavailable'}"
                    )

                else:

                    st.info("This complaint has not been assigned yet.")

                department_options = DEPARTMENTS.copy()

                if (
                    current_department
                    and current_department not in department_options
                ):

                    department_options.insert(0, current_department)

                default_department_index = (
                    department_options.index(current_department)
                    if current_department in department_options
                    else 0
                )

                selected_department = st.selectbox(
                    "Select Responsible Department",
                    department_options,
                    index=default_department_index,
                    key=f"department_{complaint_id}"
                )

                if st.button(
                    "💾 Save Department Assignment",
                    key=f"assign_{complaint_id}",
                    use_container_width=True
                ):

                    try:

                        updated = database.assign_complaint_department(
                            complaint_id,
                            selected_department
                        )

                        if updated:

                            st.success(
                                f"Complaint assigned to {selected_department}!"
                            )

                            st.rerun()

                        else:

                            st.error("Complaint could not be found.")

                    except Exception as error:

                        st.error(f"Department assignment failed: {error}")

                st.divider()

                # BEFORE AND AFTER REPAIR VERIFICATION

                st.markdown("## 🔬 Before-and-After Repair Verification")

                st.write(
                    "Upload a photograph showing the reported problem "
                    "after the claimed repair. Gemini AI will compare "
                    "the original and new photographs."
                )

                repair_path = complaint.get("repair_image_path")

                if repair_path and Path(repair_path).exists():

                    st.markdown("### 📷 Repair Evidence")

                    before_col, after_col = st.columns(2)

                    with before_col:

                        if image_path and Path(image_path).exists():

                            st.image(
                                image_path,
                                caption="BEFORE — Original Problem",
                                use_container_width=True
                            )

                    with after_col:

                        st.image(
                            repair_path,
                            caption="AFTER — Repair Evidence",
                            use_container_width=True
                        )

                    raw_analysis = complaint.get("repair_analysis")

                    if raw_analysis:

                        try:

                            repair_analysis = (
                                json.loads(raw_analysis)
                                if isinstance(raw_analysis, str)
                                else raw_analysis
                            )

                            st.markdown("### 🤖 AI Comparison Result")

                            repair_status = repair_analysis.get(
                                "repair_status", "Unknown"
                            )

                            confidence = repair_analysis.get(
                                "confidence", "Unknown"
                            )

                            st.metric(
                                "AI Estimated Repair Status",
                                repair_status
                            )

                            st.write("**AI Confidence:**", confidence)

                            st.write(
                                "**Explanation:**",
                                repair_analysis.get("explanation", "")
                            )

                            st.write(
                                "**Remaining Problem:**",
                                repair_analysis.get("remaining_problem", "")
                            )

                            st.caption(
                                "AI comparison is an estimate based on "
                                "visible evidence. It is not proof of "
                                "official repair."
                            )

                        except (ValueError, TypeError, AttributeError):

                            st.error("Could not read the saved AI comparison.")

                    st.caption(
                        "Repair evidence uploaded at: "
                        + str(complaint.get("repair_uploaded_at") or "Unknown")
                    )

                else:

                    st.info("No repair photograph has been uploaded yet.")

                # UPLOAD REPAIR PHOTOGRAPH

                st.markdown("### 📤 Upload After-Repair Photograph")

                repair_upload = st.file_uploader(
                    "Choose repair evidence photograph",
                    type=["jpg", "jpeg", "png"],
                    key=f"repair_upload_{complaint_id}"
                )

                if st.button(
                    "🤖 Compare Before and After with Gemini AI",
                    key=f"compare_repair_{complaint_id}",
                    use_container_width=True
                ):

                    if not image_path or not Path(image_path).exists():

                        st.error("Original complaint photograph is unavailable.")

                    elif repair_upload is None:

                        st.warning("Please upload an after-repair photograph first.")

                    else:

                        try:

                            before_bytes = Path(image_path).read_bytes()
                            after_bytes = repair_upload.getvalue()

                            before_suffix = Path(image_path).suffix.lower()

                            before_mime = (
                                "image/jpeg"
                                if before_suffix in [".jpg", ".jpeg"]
                                else "image/png"
                            )

                            with st.spinner(
                                "Gemini AI is comparing both photographs..."):

                                comparison = compare_repair_images(
                                    before_bytes,
                                    after_bytes,
                                    before_mime,
                                    repair_upload.type
                                )

                            if comparison["success"]:

                                analysis_result = comparison["analysis"]

                                saved_path = save_repair_image(
                                    repair_upload,
                                    complaint_id
                                )

                                saved = save_repair_evidence(
                                    complaint_id,
                                    saved_path,
                                    analysis_result
                                )

                                if saved:

                                    st.success(
                                        "Repair photograph and AI comparison saved!"
                                    )

                                    st.rerun()

                                else:

                                    st.error("Could not save repair evidence.")

                            else:

                                st.error(
                                    "Gemini comparison failed: "
                                    + str(comparison["error"])
                                )

                        except Exception as error:

                            st.error(
                                f"Repair verification error: {error}"
                            )

                # UPDATED ADMIN DECISION

                st.markdown("### 🛡️ Admin Resolution Decision")

                raw_analysis = complaint.get("repair_analysis")

                if verified:

                    st.success(
                        "✅ Repair resolution has been confirmed by admin."
                    )

                if repair_path and raw_analysis:

                    try:

                        saved_analysis = (
                            json.loads(raw_analysis)
                            if isinstance(raw_analysis, str)
                            else raw_analysis
                        )

                        if not isinstance(saved_analysis, dict):
                            raise ValueError("Invalid AI analysis format.")

                        ai_repair_status = str(
                            saved_analysis.get("repair_status", "Unknown")
                        ).strip()

                        confidence = saved_analysis.get(
                            "confidence", "Unknown"
                        )

                        explanation = saved_analysis.get(
                            "explanation",
                            "No explanation provided."
                        )

                        remaining_problem = saved_analysis.get(
                            "remaining_problem",
                            "No remaining-problem details provided."
                        )

                        st.markdown("#### 🤖 Complete AI Comparison Report")

                        result_col1, result_col2 = st.columns(2)

                        result_col1.metric(
                            "AI Estimated Repair Status",
                            ai_repair_status
                        )

                        result_col2.metric(
                            "AI Confidence",
                            str(confidence)
                        )

                        st.markdown("**📝 AI Explanation**")
                        st.info(str(explanation))

                        st.markdown("**⚠️ Remaining Visible Problem**")
                        st.warning(str(remaining_problem))

                        st.caption(
                            "This AI assessment is based only on visible "
                            "photographic evidence. It is not official proof "
                            "of repair."
                        )

                        st.divider()

                        normalized_status = ai_repair_status.casefold()

                        if not verified:

                            st.markdown("#### Admin Review")

                            st.write(
                                "Review the original photograph, repair "
                                "photograph, and complete AI report before "
                                "making a decision."
                            )

                            if normalized_status == "fixed":

                                st.success(
                                    "AI estimates that the visible issue "
                                    "appears to be fixed."
                                )

                                if st.button(
                                    "✅ Confirm Repair and Mark Resolved",
                                    key=f"confirm_repair_{complaint_id}",
                                    use_container_width=True
                                ):

                                    if confirm_repair_resolution(complaint_id):

                                        st.success(
                                            "Repair confirmed. Complaint marked Resolved!"
                                        )

                                        st.rerun()

                                    else:

                                        st.error(
                                            "Could not confirm this repair."
                                        )

                            else:

                                st.warning(
                                    "AI has not classified this repair as "
                                    "Fixed. Do not automatically mark it "
                                    "as resolved."
                                )

                                if st.button(
                                    "❌ Reject Resolution — Keep In Progress",
                                    key=f"reject_repair_{complaint_id}",
                                    use_container_width=True
                                ):

                                    if reject_repair_resolution(complaint_id):

                                        st.info(
                                            "Resolution rejected. "
                                            "Complaint remains In Progress."
                                        )

                                        st.rerun()

                                    else:

                                        st.error(
                                            "Could not update repair decision."
                                        )

                    except (ValueError, TypeError, AttributeError) as error:

                        st.error(
                            f"Could not read the saved AI comparison: {error}"
                        )

                else:

                    st.info(
                        "Upload and compare an after-repair photograph "
                        "before making a resolution decision."
                    )

                st.divider()

                # STATUS MANAGEMENT

                st.markdown("### 🔄 Complaint Status Management")

                allowed_statuses = STATUSES.copy()

                if not verified:

                    allowed_statuses.remove("Resolved")

                if current_status == "Resolved" and not verified:

                    st.warning(
                        "This complaint is marked Resolved without a "
                        "verified repair. Please review it and update "
                        "the status."
                    )

                if current_status == "Resolved" and verified:

                    st.success(
                        "This complaint has a confirmed repair resolution."
                    )

                else:

                    current_index = (
                        allowed_statuses.index(current_status)
                        if current_status in allowed_statuses
                        else 0
                    )

                    selected_status = st.selectbox(
                        "Update Complaint Status",
                        allowed_statuses,
                        index=current_index,
                        key=f"status_{complaint_id}"
                    )

                    if st.button(
                        "Save Status",
                        key=f"save_{complaint_id}",
                        use_container_width=True
                    ):

                        try:

                            updated = database.update_complaint_status(
                                complaint_id,
                                selected_status
                            )

                            if updated:

                                st.success("Complaint status updated!")

                                st.rerun()

                            else:

                                st.error("Complaint could not be found.")

                        except Exception as error:

                            st.error(
                                f"Status update failed: {error}"
                            )

        st.divider()

        # DEPARTMENT SUMMARY

        st.subheader("📊 Department Assignment Summary")

        summary_data = pd.DataFrame(complaints)

        summary_data["assigned_department"] = (
            summary_data["assigned_department"]
            .fillna("Not Assigned")
            .replace("", "Not Assigned")
        )

        department_summary = (
            summary_data.groupby("assigned_department")
            .size()
            .reset_index(name="Complaints")
        )

        department_summary.columns = [
            "Department",
            "Total Complaints"
        ]

        st.dataframe(
            department_summary,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info("No complaints available.")
