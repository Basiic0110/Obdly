# image_analysis.py - Vision analysis for OBDly with Car Identification

import base64
import streamlit as st
from openai import OpenAI
from datetime import datetime, date
import os
import json

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OBDLY_key2"))


# ═══════════════════ CAR IDENTIFICATION ═══════════════════
def identify_car_from_image(image_obj, filename: str | None = None):
    """
    Identify car make, model, and year from an image.
    
    Returns:
        dict: {"make": str, "model": str, "year": str, "confidence": str, "identified": bool}
    """
    import mimetypes

    try:
        # Normalize input to bytes
        image_bytes = None
        mime_type = None
        file_name = filename or "upload.jpg"

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
            try:
                image_obj.seek(0)
            except Exception:
                pass

        elif isinstance(image_obj, (bytes, bytearray)):
            image_bytes = bytes(image_obj)
        else:
            return {"identified": False, "error": "Unsupported image format"}

        if not image_bytes:
            return {"identified": False, "error": "Could not read image"}

        # Guess MIME type
        if not mime_type and file_name:
            guessed, _ = mimetypes.guess_type(file_name)
            mime_type = guessed or "image/jpeg"
        if not mime_type:
            mime_type = "image/jpeg"

        # Base64 encode
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Car identification prompt
        system_prompt = (
            "You are a car identification expert. Analyze the image and identify the vehicle. "
            "Return ONLY a JSON object with this exact structure:\n"
            '{"make": "manufacturer name", "model": "model name", "year": "year or year range", '
            '"confidence": "high/medium/low", "identified": true}\n\n'
            "If you cannot identify the car clearly, return:\n"
            '{"identified": false, "reason": "brief explanation"}\n\n'
            "Rules:\n"
            "- Be specific with model variants (e.g., 'Golf GTI' not just 'Golf')\n"
            "- Year can be a range like '2015-2018' if unsure of exact year\n"
            "- Only return high confidence if you're very certain\n"
            "- Consider badges, body shape, lights, wheels, and other visible features"
        )

        user_prompt = "Identify the make, model, and approximate year of this vehicle. Return only JSON."

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

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=200,
            temperature=0.3  # Lower temperature for more consistent JSON
        )

        result_text = response.choices[0].message.content.strip()

        # Try to extract JSON if wrapped in markdown code blocks
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split(
                "```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        # Parse JSON
        result = json.loads(result_text)
        return result

    except json.JSONDecodeError as e:
        return {
            "identified": False,
            "error": f"Could not parse response: {str(e)}"
        }
    except Exception as e:
        return {"identified": False, "error": str(e)}


# ═══════════════════ IMAGE ANALYSIS CORE ═══════════════════
def analyze_car_image(image_obj,
                      user_question: str = "",
                      filename: str | None = None,
                      skip_car_id: bool = False):
    """
    Analyze car image using GPT-4o-mini vision.
    
    Args:
        image_obj: Streamlit UploadedFile or raw bytes
        user_question: Optional context from user
        filename: Optional filename
        skip_car_id: If True, skip car identification step

    Returns:
        str: Analysis result
    """
    import mimetypes

    try:
        # --- Step 1: Try to identify the car first (unless skipped) ---
        car_info = None
        if not skip_car_id:
            car_info = identify_car_from_image(image_obj, filename)
            if car_info.get("identified") and car_info.get("confidence") in [
                    "high", "medium"
            ]:
                # Store in session for potential use
                st.session_state["detected_car"] = car_info

        # --- Step 2: Normalize input to (bytes, mime, name) ---
        image_bytes = None
        mime_type = None
        file_name = filename or "upload.jpg"

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
            try:
                image_obj.seek(0)
            except Exception:
                pass

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

        # Build prompts with car context if identified
        car_context = ""
        if car_info and car_info.get("identified"):
            make = car_info.get("make", "")
            model = car_info.get("model", "")
            year = car_info.get("year", "")
            car_context = f"\n\n[VEHICLE DETECTED: {make} {model} {year}]\n"

        system_prompt = (
            "You're OBDly, a UK-based car diagnostic assistant analyzing photos. "
            + car_context + "Identify:\n"
            "- Dashboard warning lights (describe colour, symbol, meaning)\n"
            "- Visible mechanical issues\n"
            "- Damage or leaks\n"
            "- OBD2 error codes if shown\n"
            "- Any safety concerns\n\n"
            "Be specific, use UK terminology (bonnet, boot, tyre), "
            "suggest if it's DIY-fixable or needs a mechanic, "
            "and estimate UK costs where relevant. "
            "Include make/model-specific advice where possible.")

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

        analysis = response.choices[0].message.content

        # Prepend car identification if detected
        if car_info and car_info.get("identified"):
            make = car_info.get("make", "")
            model = car_info.get("model", "")
            year = car_info.get("year", "")
            conf = car_info.get("confidence", "medium")

            car_header = f"🚗 **Detected Vehicle:** {make} {model} {year} ({conf} confidence)\n\n"
            analysis = car_header + analysis

        return analysis

    except Exception as e:
        return f"⚠️ Image analysis failed: {str(e)}\n\nPlease try again or describe the issue in text."


def show_car_identification_confirmation():
    """
    Show UI to confirm detected car and optionally populate vehicle data
    Returns: bool (whether user confirmed)
    """
    if "detected_car" not in st.session_state:
        return False

    car_info = st.session_state["detected_car"]
    if not car_info.get("identified"):
        return False

    make = car_info.get("make", "")
    model = car_info.get("model", "")
    year = car_info.get("year", "")
    confidence = car_info.get("confidence", "medium")

    if not make or not model:
        return False

    # Only show if we don't already have a vehicle set
    if st.session_state.get("vehicle"):
        return False

    st.info(
        f"🚗 I detected this might be a **{make} {model} ({year})** - {confidence} confidence"
    )

    col1, col2, col3 = st.columns([2, 2, 3])

    with col1:
        if st.button("✅ Yes, that's correct",
                     key="confirm_car_yes",
                     use_container_width=True):
            # Populate vehicle session state
            st.session_state["vehicle"] = {
                "make": make,
                "model": model,
                "yearOfManufacture": year.split("-")[0]
                if "-" in year else year,  # Take first year if range
                "registrationNumber": "DETECTED_FROM_IMAGE",
                "_source": "Image Detection"
            }
            st.session_state[
                "detected_car"] = None  # Clear so we don't ask again
            st.success(f"✅ Vehicle set to {make} {model}")
            st.rerun()
            return True

    with col2:
        if st.button("❌ No, that's wrong",
                     key="confirm_car_no",
                     use_container_width=True):
            st.session_state["detected_car"] = None  # Clear detection
            st.info(
                "No problem - you can enter your registration manually above")
            return False

    with col3:
        st.caption("This helps me give better advice")

    return False


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

                # Show car identification confirmation if detected
                show_car_identification_confirmation()

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
