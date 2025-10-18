# image_analysis.py - Vision analysis for OBDly

import base64
import streamlit as st
from openai import OpenAI
from datetime import datetime, date
import os

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OBDLY_key2"))


# ═══════════════════ IMAGE ANALYSIS CORE ═══════════════════
def analyze_car_image(image_obj,
                      user_question: str = "",
                      filename: str | None = None):
    """
    Analyze car image using GPT-4o-mini vision.

    Args:
        image_obj: Streamlit UploadedFile or raw bytes
        user_question: Optional context from user
        filename: Optional filename (used to infer MIME if bytes provided)

    Returns:
        str: Analysis result
    """
    import mimetypes

    try:
        # --- Normalise input to (bytes, mime, name) ---
        image_bytes = None
        mime_type = None
        file_name = filename or "upload.jpg"

        # Case 1: UploadedFile / file-like
        if hasattr(image_obj, "read"):
            try:
                file_name = getattr(image_obj, "name", file_name) or file_name
            except Exception:
                pass
            try:
                mime_type = getattr(image_obj, "type", None)
            except Exception:
                mime_type = None

            image_bytes = image_obj.read()
            # rewind so the object can be reused later if needed
            try:
                image_obj.seek(0)
            except Exception:
                pass

        # Case 2: raw bytes
        elif isinstance(image_obj, (bytes, bytearray)):
            image_bytes = bytes(image_obj)

        else:
            return "⚠️ Unsupported image object. Please re-upload the photo."

        if not image_bytes:
            return "⚠️ I couldn't read the image data. Please try re-uploading."

        # Guess MIME if missing
        if not mime_type and file_name:
            guessed, _ = mimetypes.guess_type(file_name)
            mime_type = guessed or "image/jpeg"
        if not mime_type:
            mime_type = "image/jpeg"

        # Base64 encode
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Build prompts
        system_prompt = (
            "You're OBDly, a UK-based car diagnostic assistant analyzing photos. "
            "Identify:\n"
            "- Dashboard warning lights (describe colour, symbol, meaning)\n"
            "- Visible mechanical issues\n"
            "- Damage or leaks\n"
            "- OBD2 error codes if shown\n"
            "- Any safety concerns\n\n"
            "Be specific, use UK terminology (bonnet, boot, tyre), "
            "suggest if it's DIY-fixable or needs a mechanic, "
            "and estimate UK costs where relevant.")

        user_prompt = user_question or "What can you see wrong with this car? Please analyse the image in detail."

        messages = [{
            "role": "system",
            "content": system_prompt
        }, {
            "role":
            "user",
            "content": [{
                "type": "text",
                "text": user_prompt
            }, {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_image}",
                    "detail": "high"
                }
            }]
        }]

        response = client.chat.completions.create(model="gpt-4o-mini",
                                                  messages=messages,
                                                  max_tokens=600,
                                                  temperature=0.6)

        return response.choices[0].message.content

    except Exception as e:
        return f"⚠️ Image analysis failed: {str(e)}\n\nPlease try again or describe the issue in text."


# ═══════════════════ RATE LIMITING ═══════════════════
def check_image_limit():
    """
    Check if user has exceeded daily image limit
    Returns: (bool: can_upload, int: remaining, str: message)
    """
    ss = st.session_state

    if "image_counter_day" not in ss:
        ss.image_counter_day = date.today().isoformat()
        ss.images_today = 0

    if ss.image_counter_day != date.today().isoformat():
        ss.image_counter_day = date.today().isoformat()
        ss.images_today = 0

    is_premium = ss.get("is_premium", False)
    if is_premium:
        return True, "unlimited", "✨ Premium: Unlimited images"

    FREE_LIMIT = 3
    remaining = FREE_LIMIT - ss.images_today
    if remaining > 0:
        return True, remaining, f"📸 {remaining} image{'s' if remaining != 1 else ''} remaining today (free tier)"
    else:
        return False, 0, "❌ Daily limit reached (3 images). Upgrade to Premium for unlimited!"


def increment_image_count():
    """Increment the daily image counter"""
    ss = st.session_state
    if not ss.get("is_premium", False):
        ss.images_today = ss.get("images_today", 0) + 1


def log_image_analysis(filename: str, analysis: str):
    """Log image analysis for tracking"""
    try:
        import csv
        with open("image_log.csv", "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if f.tell() == 0:
                w.writerow(["Timestamp", "Filename", "Analysis", "User Type"])
            w.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), filename,
                analysis[:200],
                "Premium" if st.session_state.get("is_premium") else "Free"
            ])
    except Exception:
        pass


# ═══════════════════ UI COMPONENTS ═══════════════════
def show_image_uploader():
    """
    Show image uploader with rate limiting
    Returns: (uploaded_file, analysis_result) or (None, None)
    """
    can_upload, remaining, message = check_image_limit()

    if can_upload:
        st.info(message)
    else:
        st.error(message)
        st.markdown("### 🌟 Upgrade to Premium")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("⭐ Get Premium - £2.99/month",
                         use_container_width=True,
                         key="premium_upgrade"):
                st.info(
                    "Premium coming soon! Email [email protected] to get early access."
                )
        return None, None

    uploaded_file = st.file_uploader(
        "📸 Upload photo of your car issue",
        type=["png", "jpg", "jpeg", "heic"],
        help="Dashboard lights, engine bay, visible damage, OBD2 codes, etc.",
        key="image_upload_main")

    if uploaded_file:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.image(uploaded_file,
                     caption="Your upload",
                     use_column_width=True)
        with col2:
            st.markdown("**Tips for best results:**")
            st.markdown("- Clear, well-lit photo")
            st.markdown("- Focus on the issue")
            st.markdown("- Multiple angles help")
            st.markdown("- Include context")

        context = st.text_input(
            "Add context (optional)",
            placeholder="e.g. 'This light came on after I drove through water'",
            key="image_context")

        if st.button("🔍 Analyze Image",
                     use_container_width=True,
                     type="primary",
                     key="analyze_btn"):
            with st.spinner("🤖 OBDly is analyzing your image..."):
                analysis = analyze_car_image(uploaded_file, context)
                increment_image_count()
                log_image_analysis(uploaded_file.name, analysis)
                return uploaded_file, analysis

    return None, None


def show_premium_promo():
    """Show premium upgrade promotion"""
    if st.session_state.get("is_premium"):
        return

    with st.expander("⭐ Upgrade to Premium", expanded=False):
        st.markdown("### 🌟 OBDly Premium - £2.99/month")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **✨ Premium Benefits:**
            - 🔓 Unlimited image uploads
            - 📹 Video analysis (coming soon)
            - ⚡ Priority support
            - 🎯 Advanced diagnostics
            - 💾 Save diagnosis history
            - 📊 Track repair costs
            """)
        with col2:
            st.markdown("""
            **💷 Value:**
            - Free: 3 images/day
            - Premium: Unlimited
            - Save £100s on mechanic visits
            - Cancel anytime
            
            **Coming Soon:**
            - Photo damage quotes
            - Insurance claims support
            """)

        if st.button("🚀 Get Premium Now",
                     use_container_width=True,
                     key="premium_promo"):
            st.balloons()
            st.info("""
            **Premium launching soon!**
            
            Email [email protected] with:
            - Your email
            - "I want Premium"
            
            Early supporters get 50% off for life! (£1.49/month)
            """)


# ═══════════════════ INTEGRATION WITH CHAT ═══════════════════
def add_image_to_chat_message(image_file, analysis: str):
    """Add image analysis to chat messages"""
    ss = st.session_state
    ts = datetime.now().strftime("%H:%M")
    ss.chat_messages.append({
        "role": "user",
        "content": f"📸 [Uploaded image: {image_file.name}]",
        "timestamp": ts,
        "has_image": True,
        "image_file": image_file
    })
    ss.chat_messages.append({
        "role": "assistant",
        "content": f"📸 **Image Analysis:**\n\n{analysis}",
        "timestamp": ts,
        "type": "image_analysis"
    })


# ═══════════════════ ADMIN TRACKING ═══════════════════
def show_image_analytics():
    """Show image usage analytics for admin"""
    try:
        import csv
        import pandas as pd
        with open("image_log.csv", "r", encoding="utf-8") as f:
            df = pd.read_csv(f)

        st.markdown("## 📊 Image Analysis Stats")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Images", len(df))
        with col2:
            st.metric("Free Tier Images", len(df[df['User Type'] == 'Free']))
        with col3:
            st.metric("Premium Images", len(df[df['User Type'] == 'Premium']))

        st.markdown("### Recent Uploads")
        for _, row in df.tail(10).iterrows():
            with st.expander(f"[{row['Timestamp']}] {row['Filename']}"):
                st.markdown(f"**Type:** {row['User Type']}")
                st.markdown(f"**Analysis:** {row['Analysis']}")
    except FileNotFoundError:
        st.info("No image data yet")
    except Exception as e:
        st.error(f"Error loading analytics: {e}")
