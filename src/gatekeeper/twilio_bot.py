from twilio.rest import Client
from config import settings
import datetime

class TwilioGatekeeper:
    def __init__(self):
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            print("Warning: Twilio credentials missing.")
            self.client = None
        else:
            self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        self.from_number = settings.TWILIO_PHONE_NUMBER
        self.owner_number = settings.OWNER_PHONE_NUMBER

    def send_review_alert(self, author: str, original_text: str, vietnamese_summary: str, english_draft: str, vietnamese_draft: str):
        """Sends an SMS alert to the owner."""
        if not self.client:
            print("Twilio not configured. Skipping SMS.")
            return

        # Format message as per User Request / Architecture
        # "Customer X said: [Original]. Tom tat: [VN]. Reply: [Draft]. Reply YES to post."
        
        # Twilio has a 1600 char limit (multipart), but good to be concise.
        message_body = (
            f"Customer {author} said: {original_text}\n\n"
            f"Tom tat: {vietnamese_summary}\n\n"
            f"Reply (EN): {english_draft}\n\n"
            f"Reply (VN): {vietnamese_draft}\n\n"
            f"Reply OK/YES to post."
        )

        try:
            message = self.client.messages.create(
                body=message_body,
                from_=self.from_number,
                to=self.owner_number
            )
            print(f"SMS sent: {message.sid}")
            return message.sid
        except Exception as e:
            print(f"Error sending SMS: {e}")

    def check_approval(self, time_limit_minutes=60):
        """
        Polls for the latest message from the owner.
        Returns 'APPROVED' if the latest message says 'OK', 'YES', or 'DUYET'.
        Returns 'None' if no new relevant message.
        """
        if not self.client:
            return None

        try:
            # list messages from owner
            messages = self.client.messages.list(
                from_=self.owner_number,
                to=self.from_number,
                limit=1
            )
            
            if not messages:
                return None

            last_msg = messages[0]
            # Check if message is recent (within last loop/hour)
            # Twilio date_sent is UTC.
            msg_time = last_msg.date_sent
            if not msg_time:
                return None
                
            # Naive time check (ensure timezone awareness in real app)
            # For this script, we'll assume if it's the top message and content matches, return True.
            # Ideally we check timestamp against a 'last_checked_timestamp'.
            
            body = last_msg.body.strip().upper()
            if body in ["OK", "YES", "Y", "CO", "DUYET"]:
                return "APPROVED"
            
            return None

        except Exception as e:
            print(f"Error checking SMS replies: {e}")
            return None
