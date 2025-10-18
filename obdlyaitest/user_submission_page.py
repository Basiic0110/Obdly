# user_submission_page.py - Add this to your main app

import streamlit as st
import csv
from datetime import datetime
import os


def submission_page():
    """User submission system for community fixes"""

    st.markdown("## 🛠️ Share Your Fix")
    st.markdown("""
    Help the OBDly community! Share a fix that worked for you and help other drivers solve the same problem.

    **Why contribute?**
    - Help thousands of other drivers
    - Build your reputation score
    - Get priority support
    - Early access to new features
    """)

    # Submission form
    with st.form("user_submission_form", clear_on_submit=True):
        st.markdown("### Your Car Details")
        col1, col2, col3 = st.columns(3)

        with col1:
            make = st.text_input("Make*", placeholder="e.g. Ford")
        with col2:
            model = st.text_input("Model*", placeholder="e.g. Focus")
        with col3:
            year = st.text_input("Year*", placeholder="e.g. 2018")

        st.markdown("### The Problem")
        fault = st.text_area(
            "What was wrong?*",
            placeholder=
            "Describe the fault clearly - e.g. 'Engine juddering at low speeds with check engine light'",
            height=100)

        symptoms = st.text_area(
            "Symptoms (optional)",
            placeholder="Warning lights, sounds, when it happens, etc.",
            height=80)

        st.markdown("### Your Fix")
        fix = st.text_area(
            "What fixed it?*",
            placeholder=
            "Detailed steps you took - e.g. 'Replaced all 4 ignition coils and spark plugs. Cleared fault codes.'",
            height=120)

        col1, col2, col3 = st.columns(3)
        with col1:
            cost = st.text_input("Cost (£)", placeholder="e.g. 250")
        with col2:
            urgency = st.selectbox("Urgency*", ["Low", "Medium", "High"],
                                   help="How urgent is this to fix?")
        with col3:
            difficulty = st.selectbox("Difficulty*",
                                      ["DIY", "Intermediate", "Professional"],
                                      help="Can average person do this?")

        warning_light = st.radio("Was there a warning light?",
                                 ["Yes", "No", "Not sure"],
                                 horizontal=True)

        # Verification questions (helps filter spam)
        st.markdown("### Verification")

        col1, col2 = st.columns(2)
        with col1:
            did_it_work = st.radio("Did this fix work?*", [
                "Yes - completely fixed", "Yes - mostly fixed", "Partially",
                "No"
            ],
                                   help="Be honest - it helps everyone")
        with col2:
            mechanic_verified = st.radio(
                "Was this done by/verified by a mechanic?", ["Yes", "No"],
                help="Professional verification adds credibility")

        # Contact (optional for follow-up)
        st.markdown("### Contact (Optional)")
        st.caption("We may contact you to verify details or feature your fix")

        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name", placeholder="Optional")
        with col2:
            email = st.text_input("Email", placeholder="Optional")

        # Terms
        agree = st.checkbox(
            "I confirm this information is accurate and I give OBDly permission to use it*",
            value=False)

        # Submit button
        col1, col2, col3 = st.columns([2, 1, 2])
        with col2:
            submitted = st.form_submit_button("🚀 Submit Fix",
                                              use_container_width=True)

    # Handle submission
    if submitted:
        # Validation
        if not all([make, model, year, fault, fix, urgency, difficulty]):
            st.error("❌ Please fill in all required fields (marked with *)")
            return

        if not agree:
            st.error("❌ Please agree to the terms to submit")
            return

        if did_it_work in ["No", "Partially"]:
            st.warning(
                "⚠️ Thanks for your honesty! We'll mark this as 'needs verification' before adding to the database."
            )

        # Save to pending submissions
        save_submission({
            "timestamp":
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "make":
            make.title(),
            "model":
            model.title(),
            "year":
            year,
            "fault":
            fault,
            "symptoms":
            symptoms,
            "fix":
            fix,
            "cost":
            cost or "Unknown",
            "urgency":
            urgency,
            "difficulty":
            difficulty,
            "warning_light":
            warning_light,
            "success_level":
            did_it_work,
            "mechanic_verified":
            mechanic_verified,
            "name":
            name or "Anonymous",
            "email":
            email or "Not provided",
            "status":
            "pending"
        })

        st.success(
            "✅ **Submission received!** Thank you for contributing to the OBDly community!"
        )
        st.balloons()

        st.info("""
        **What happens next?**
        1. Our team will review your submission (usually within 48 hours)
        2. If approved, it'll be added to the database
        3. You'll earn reputation points (coming soon!)
        4. Other users will benefit from your knowledge
        """)


def save_submission(data):
    """Save user submission to pending CSV"""
    filename = "pending_submissions.csv"
    file_exists = os.path.exists(filename)

    try:
        with open(filename, "a", newline="", encoding="utf-8") as f:
            fieldnames = [
                "timestamp", "make", "model", "year", "fault", "symptoms",
                "fix", "cost", "urgency", "difficulty", "warning_light",
                "success_level", "mechanic_verified", "name", "email", "status"
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            if not file_exists:
                writer.writeheader()

            writer.writerow(data)
        return True
    except Exception as e:
        st.error(f"Error saving submission: {e}")
        return False


def admin_review_page():
    """Admin page to review and approve submissions"""
    st.markdown("## 📋 Review Submissions")

    if not os.path.exists("pending_submissions.csv"):
        st.info("No pending submissions yet!")
        return

    try:
        with open("pending_submissions.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            submissions = list(reader)
    except:
        st.error("Error loading submissions")
        return

    pending = [s for s in submissions if s.get("status") == "pending"]

    if not pending:
        st.success("✅ All caught up! No pending submissions.")
        return

    st.info(f"**{len(pending)} pending submissions** to review")

    for idx, sub in enumerate(pending):
        with st.expander(
                f"[{sub['timestamp']}] {sub['make']} {sub['model']} {sub['year']} - {sub['fault'][:50]}..."
        ):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(
                    f"**Car:** {sub['make']} {sub['model']} {sub['year']}")
                st.markdown(f"**Fault:** {sub['fault']}")
                if sub['symptoms']:
                    st.markdown(f"**Symptoms:** {sub['symptoms']}")
                st.markdown(f"**Fix:** {sub['fix']}")
                st.markdown(f"**Cost:** £{sub['cost']}")
                st.markdown(f"**Urgency:** {sub['urgency']}")
                st.markdown(f"**Difficulty:** {sub['difficulty']}")
                st.markdown(f"**Warning Light:** {sub['warning_light']}")
                st.markdown(f"**Success Level:** {sub['success_level']}")
                st.markdown(
                    f"**Mechanic Verified:** {sub['mechanic_verified']}")
                st.markdown(
                    f"**Submitted by:** {sub['name']} ({sub['email']})")

            with col2:
                if st.button("✅ Approve", key=f"approve_{idx}"):
                    approve_submission(sub, idx)
                    st.rerun()

                if st.button("❌ Reject", key=f"reject_{idx}"):
                    reject_submission(idx)
                    st.rerun()

                if st.button("📝 Edit & Approve", key=f"edit_{idx}"):
                    st.info("Edit feature coming soon!")


def approve_submission(submission, idx):
    """Approve and add to main database"""
    # Add to main fault database
    with open("obdly_fault_data.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            submission['make'],
            submission['model'],
            submission['year'],
            submission['fault'],
            submission['fix'],
            submission['urgency'],
            submission['warning_light'],
            f"£{submission['cost']}"
            if submission['cost'] != "Unknown" else "Unknown",
            submission['difficulty'],
            1  # Initial user report count
        ])

    # Update status in pending
    update_submission_status(idx, "approved")

    st.success(f"✅ Approved! Added to database.")


def reject_submission(idx):
    """Reject submission"""
    update_submission_status(idx, "rejected")
    st.info("Submission rejected")


def update_submission_status(idx, new_status):
    """Update submission status"""
    try:
        with open("pending_submissions.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            submissions = list(reader)

        submissions[idx]["status"] = new_status

        with open("pending_submissions.csv", "w", newline="",
                  encoding="utf-8") as f:
            fieldnames = submissions[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(submissions)
    except Exception as e:
        st.error(f"Error updating status: {e}")


# Add these pages to your main app sidebar
def add_to_main_app():
    """
    Add this to your main obdly_app.py sidebar:

    page = st.sidebar.radio("Menu", [
        "🔧 Diagnose", 
        "🛠️ Share Your Fix",  # NEW
        "📋 Review Submissions",  # NEW (admin only)
        "📊 Previous Queries",
        "ℹ️ About"
    ])

    if page == "🛠️ Share Your Fix":
        submission_page()
    elif page == "📋 Review Submissions":
        # Add password protection for admin
        if check_admin_access():
            admin_review_page()
        else:
            st.error("🔒 Admin access only")
    """
    pass


def check_admin_access():
    """Simple admin password check"""
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False

    if st.session_state.admin_authenticated:
        return True

    st.markdown("## 🔒 Admin Access Required")
    password = st.text_input("Enter admin password:", type="password")

    if st.button("Login"):
        # Change this password in production!
        if password == os.environ.get("ADMIN_PASSWORD", "obdly2024"):
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")

    return False
