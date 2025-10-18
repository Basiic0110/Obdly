# database_manager.py - Easy CSV management through your app

import streamlit as st
import pandas as pd
import csv
import os
from datetime import datetime


def database_manager_page():
    """Visual database manager - no CSV editing required!"""

    st.markdown("## 🗄️ Database Manager")
    st.markdown(
        "Add, edit, and manage your fault database visually - no CSV editing needed!"
    )

    # Check if file exists
    if not os.path.exists("obdly_fault_data.csv"):
        st.error("⚠️ obdly_fault_data.csv not found!")
        if st.button("Create Empty Database"):
            create_empty_database()
            st.rerun()
        return

    # Load current database
    try:
        df = pd.read_csv("obdly_fault_data.csv")
        total_faults = len(df)
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return

    # Tabs for different actions
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 View All", "➕ Add New", "✏️ Edit", "🔍 Search"])

    # ═══════════════════ TAB 1: VIEW ALL ═══════════════════
    with tab1:
        st.markdown(f"### 📊 Current Database ({total_faults} faults)")

        # Stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Faults", total_faults)
        with col2:
            high_urgency = len(df[df['Urgency'] == 'High'])
            st.metric("High Urgency", high_urgency)
        with col3:
            unique_makes = df['Make'].nunique()
            st.metric("Car Makes", unique_makes)
        with col4:
            user_reports = df['User Reports'].sum(
            ) if 'User Reports' in df.columns else 0
            st.metric("Total Reports", int(user_reports))

        # Filters
        st.markdown("#### Filters")
        col1, col2, col3 = st.columns(3)

        with col1:
            filter_make = st.selectbox("Filter by Make", ["All"] +
                                       sorted(df['Make'].unique().tolist()))
        with col2:
            filter_urgency = st.selectbox("Filter by Urgency",
                                          ["All", "High", "Medium", "Low"])
        with col3:
            filter_difficulty = st.selectbox(
                "Filter by Difficulty",
                ["All", "DIY", "Intermediate", "Professional"])

        # Apply filters
        filtered_df = df.copy()
        if filter_make != "All":
            filtered_df = filtered_df[filtered_df['Make'] == filter_make]
        if filter_urgency != "All":
            filtered_df = filtered_df[filtered_df['Urgency'] == filter_urgency]
        if filter_difficulty != "All":
            filtered_df = filtered_df[filtered_df['Difficulty'] ==
                                      filter_difficulty]

        st.markdown(f"**Showing {len(filtered_df)} of {total_faults} faults**")

        # Display table with better formatting
        if len(filtered_df) > 0:
            # Show in expandable cards for better readability
            for idx, row in filtered_df.iterrows():
                with st.expander(
                        f"{row['Make']} {row['Model']} ({row['Year']}) - {row['Fault'][:60]}..."
                ):
                    col1, col2 = st.columns([2, 1])

                    with col1:
                        st.markdown(f"**Fault:** {row['Fault']}")
                        st.markdown(f"**Fix:** {row['Suggested Fix']}")
                        st.markdown(f"**Cost:** {row['Cost Estimate']}")

                    with col2:
                        st.markdown(f"**Urgency:** {row['Urgency']}")
                        st.markdown(f"**Difficulty:** {row['Difficulty']}")
                        st.markdown(
                            f"**Warning Light:** {row['Warning Light?']}")
                        st.markdown(
                            f"**Reports:** {row.get('User Reports', 0)}")

                    # Quick actions
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✏️ Edit", key=f"edit_{idx}"):
                            st.session_state['edit_index'] = idx
                            st.session_state['edit_data'] = row.to_dict()
                            st.info("Go to 'Edit' tab to modify this entry")
                    with col2:
                        if st.button("🗑️ Delete", key=f"delete_{idx}"):
                            if delete_fault(idx):
                                st.success("Deleted!")
                                st.rerun()
        else:
            st.info("No faults match your filters")

    # ═══════════════════ TAB 2: ADD NEW ═══════════════════
    with tab2:
        st.markdown("### ➕ Add New Fault")

        with st.form("add_fault_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)

            with col1:
                make = st.text_input("Make*", placeholder="e.g. Ford")
            with col2:
                model = st.text_input("Model*", placeholder="e.g. Focus")
            with col3:
                year = st.text_input("Year/Range*",
                                     placeholder="e.g. 2015-2020")

            fault = st.text_area(
                "Fault Description*",
                placeholder="Brief description of the problem",
                height=80)

            fix = st.text_area("Suggested Fix*",
                               placeholder="Detailed steps to fix the issue",
                               height=100)

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                urgency = st.selectbox("Urgency*", ["Low", "Medium", "High"])
            with col2:
                warning = st.selectbox("Warning Light?*",
                                       ["Yes", "No", "Unknown"])
            with col3:
                cost = st.text_input("Cost Estimate*",
                                     placeholder="e.g. £100-300")
            with col4:
                difficulty = st.selectbox(
                    "Difficulty*", ["DIY", "Intermediate", "Professional"])

            user_reports = st.number_input(
                "User Reports",
                min_value=0,
                value=1,
                help="How many times this has been reported")

            col1, col2, col3 = st.columns([2, 1, 2])
            with col2:
                submitted = st.form_submit_button("💾 Add Fault",
                                                  use_container_width=True)

            if submitted:
                if not all([make, model, year, fault, fix, cost]):
                    st.error(
                        "❌ Please fill in all required fields (marked with *)")
                else:
                    new_fault = {
                        'Make': make.title(),
                        'Model': model.title(),
                        'Year': year,
                        'Fault': fault,
                        'Suggested Fix': fix,
                        'Urgency': urgency,
                        'Warning Light?': warning,
                        'Cost Estimate':
                        cost if cost.startswith('£') else f"£{cost}",
                        'Difficulty': difficulty,
                        'User Reports': user_reports
                    }

                    if add_fault(new_fault):
                        st.success("✅ Fault added successfully!")
                        st.balloons()
                        # Reload data
                        time.sleep(1)
                        st.rerun()

    # ═══════════════════ TAB 3: EDIT ═══════════════════
    with tab3:
        st.markdown("### ✏️ Edit Existing Fault")

        if 'edit_index' in st.session_state and 'edit_data' in st.session_state:
            st.info(
                f"Editing: {st.session_state['edit_data']['Make']} {st.session_state['edit_data']['Model']}"
            )

            with st.form("edit_fault_form"):
                data = st.session_state['edit_data']

                col1, col2, col3 = st.columns(3)
                with col1:
                    make = st.text_input("Make", value=data.get('Make', ''))
                with col2:
                    model = st.text_input("Model", value=data.get('Model', ''))
                with col3:
                    year = st.text_input("Year/Range",
                                         value=data.get('Year', ''))

                fault = st.text_area("Fault Description",
                                     value=data.get('Fault', ''),
                                     height=80)
                fix = st.text_area("Suggested Fix",
                                   value=data.get('Suggested Fix', ''),
                                   height=100)

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    urgency = st.selectbox(
                        "Urgency", ["Low", "Medium", "High"],
                        index=["Low", "Medium",
                               "High"].index(data.get('Urgency', 'Medium')))
                with col2:
                    warning = st.selectbox(
                        "Warning Light?", ["Yes", "No", "Unknown"],
                        index=["Yes", "No", "Unknown"
                               ].index(data.get('Warning Light?', 'Unknown')))
                with col3:
                    cost = st.text_input("Cost Estimate",
                                         value=data.get('Cost Estimate', ''))
                with col4:
                    difficulty = st.selectbox(
                        "Difficulty", ["DIY", "Intermediate", "Professional"],
                        index=["DIY", "Intermediate", "Professional"
                               ].index(data.get('Difficulty', 'Intermediate')))

                user_reports = st.number_input("User Reports",
                                               min_value=0,
                                               value=int(
                                                   data.get('User Reports',
                                                            1)))

                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.form_submit_button("💾 Save Changes",
                                             use_container_width=True):
                        updated_fault = {
                            'Make': make.title(),
                            'Model': model.title(),
                            'Year': year,
                            'Fault': fault,
                            'Suggested Fix': fix,
                            'Urgency': urgency,
                            'Warning Light?': warning,
                            'Cost Estimate': cost,
                            'Difficulty': difficulty,
                            'User Reports': user_reports
                        }

                        if update_fault(st.session_state['edit_index'],
                                        updated_fault):
                            st.success("✅ Updated successfully!")
                            del st.session_state['edit_index']
                            del st.session_state['edit_data']
                            st.rerun()

                with col2:
                    if st.form_submit_button("❌ Cancel",
                                             use_container_width=True):
                        del st.session_state['edit_index']
                        del st.session_state['edit_data']
                        st.rerun()

        else:
            st.info("👆 Select a fault from the 'View All' tab to edit it")

    # ═══════════════════ TAB 4: SEARCH ═══════════════════
    with tab4:
        st.markdown("### 🔍 Search Database")

        search_query = st.text_input(
            "Search for faults, fixes, or car models",
            placeholder="e.g. 'transmission' or 'Ford Focus'")

        if search_query:
            # Search across multiple columns
            mask = (
                df['Make'].str.contains(search_query, case=False, na=False)
                | df['Model'].str.contains(search_query, case=False, na=False)
                | df['Fault'].str.contains(search_query, case=False, na=False)
                | df['Suggested Fix'].str.contains(
                    search_query, case=False, na=False))

            results = df[mask]

            st.markdown(f"**Found {len(results)} results**")

            if len(results) > 0:
                for idx, row in results.iterrows():
                    with st.expander(
                            f"{row['Make']} {row['Model']} ({row['Year']}) - {row['Fault'][:60]}..."
                    ):
                        st.markdown(f"**Fault:** {row['Fault']}")
                        st.markdown(f"**Fix:** {row['Suggested Fix']}")
                        st.markdown(
                            f"**Cost:** {row['Cost Estimate']} | **Urgency:** {row['Urgency']} | **Difficulty:** {row['Difficulty']}"
                        )
            else:
                st.info("No results found. Try a different search term.")

    # Backup button
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 1, 2])
    with col2:
        if st.button("💾 Backup Database", use_container_width=True):
            backup_database()


# ═══════════════════ HELPER FUNCTIONS ═══════════════════


def create_empty_database():
    """Create a new empty database with headers"""
    headers = [
        'Make', 'Model', 'Year', 'Fault', 'Suggested Fix', 'Urgency',
        'Warning Light?', 'Cost Estimate', 'Difficulty', 'User Reports'
    ]

    with open('obdly_fault_data.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

    st.success("✅ Empty database created!")


def add_fault(fault_data):
    """Add a new fault to the database"""
    try:
        with open('obdly_fault_data.csv', 'a', newline='',
                  encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fault_data.keys())
            writer.writerow(fault_data)
        return True
    except Exception as e:
        st.error(f"Error adding fault: {e}")
        return False


def update_fault(index, updated_data):
    """Update an existing fault"""
    try:
        df = pd.read_csv('obdly_fault_data.csv')

        # Update the row
        for key, value in updated_data.items():
            df.at[index, key] = value

        # Save back to CSV
        df.to_csv('obdly_fault_data.csv', index=False)
        return True
    except Exception as e:
        st.error(f"Error updating fault: {e}")
        return False


def delete_fault(index):
    """Delete a fault from the database"""
    try:
        df = pd.read_csv('obdly_fault_data.csv')
        df = df.drop(index)
        df.to_csv('obdly_fault_data.csv', index=False)
        return True
    except Exception as e:
        st.error(f"Error deleting fault: {e}")
        return False


def backup_database():
    """Create a timestamped backup of the database"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"obdly_fault_data_backup_{timestamp}.csv"

        df = pd.read_csv('obdly_fault_data.csv')
        df.to_csv(backup_name, index=False)

        st.success(f"✅ Backup created: {backup_name}")
        st.info("Download it from the files panel to keep a safe copy!")
    except Exception as e:
        st.error(f"Error creating backup: {e}")


# ═══════════════════ INTEGRATION INSTRUCTIONS ═══════════════════
"""
TO ADD TO YOUR MAIN APP:

1. Install pandas (if not already):
   pip install pandas

2. Create this file as database_manager.py in Replit

3. Add to your obdly_app.py sidebar:

   from database_manager import database_manager_page

   page = st.sidebar.radio("Menu", [
       "🔧 Diagnose",
       "🛠️ Share Your Fix",
       "🗄️ Database Manager",  # NEW - Admin only
       "🔍 Reddit Collector",
       "📋 Review Submissions",
       "📊 Previous Queries",
       "ℹ️ About"
   ])

   if page == "🗄️ Database Manager":
       if check_admin_access():  # Use your existing admin check
           database_manager_page()
       else:
           st.error("🔒 Admin access only")

4. Now you can manage your database visually - no CSV editing needed!
"""
