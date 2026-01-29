import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.processing.router import IntelligenceRouter

class TestIntelligenceRouter(unittest.TestCase):
    @patch('src.processing.router.genai')
    @patch('src.processing.router.Anthropic')
    @patch('src.processing.router.OpenAI')
    @patch('src.processing.router.settings')
    def test_router_flow(self, mock_settings, mock_openai, mock_anthropic, mock_genai):
        # Mock Settings
        mock_settings.GEMINI_API_KEY = "fake_key"
        mock_settings.GEMINI_MODEL_NAME = "gemini-1.5-flash"
        mock_settings.CLAUDE_API_KEY = "fake_claude"
        mock_settings.DEEPSEEK_API_KEY = "fake_deepseek"

        # Mock Gemini (Scout & Draft)
        mock_gemini_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_gemini_model
        
        # Scout Response (Simple)
        mock_gemini_model.generate_content.side_effect = [
            MagicMock(text='{"sentiment": "Positive", "tags": ["Service"], "is_complex": false}'), # Scout
            MagicMock(text='Thank you contextually.') # Draft
        ]

        # Init Router
        router = IntelligenceRouter()
        
        # Test 1: Simple Positive Review
        result = router.process_review(
            text="Great service!", 
            author="Alice", 
            rating=5, 
            context_image_path=None
        )
        
        # Verify: Claude NOT called
        self.assertFalse(router.claude_client.messages.create.called)
        
        # Verify: Gemini Draft called
        self.assertEqual(result['english_reply'], "Thank you contextually.")

    @patch('src.processing.router.genai')
    @patch('src.processing.router.Anthropic')
    @patch('src.processing.router.OpenAI')
    @patch('src.processing.router.settings')
    def test_complex_negative_review(self, mock_settings, mock_openai, mock_anthropic, mock_genai):
        # Mock Settings
        mock_settings.GEMINI_API_KEY = "fake_key"
        mock_settings.CLAUDE_API_KEY = "fake_claude"
        mock_settings.DEEPSEEK_API_KEY = "fake_deepseek"
        
        # Mock Gemini
        mock_gemini_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_gemini_model
        
        # Scout says Negative
        mock_gemini_model.generate_content.side_effect = [
            MagicMock(text='{"sentiment": "Negative", "tags": ["Rude"], "is_complex": true}'), # Scout
            MagicMock(text='Apology draft.') # Draft
        ]
        
        # Mock Claude
        mock_claude_client = MagicMock()
        mock_anthropic.return_value = mock_claude_client
        mock_claude_client.messages.create.return_value.content = [MagicMock(text="Context: Owner needs to know...")]
        
        # Mock DeepSeek
        mock_deepseek_client = MagicMock()
        mock_openai.return_value = mock_deepseek_client
        mock_deepseek_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='{"vietnamese_summary": "Khách giận", "vietnamese_reply": "Xin lỗi"}'))
        ]

        # Init Router
        router = IntelligenceRouter()
        
        # Test 2: Negative Review
        result = router.process_review(
            text="Service was rude.", 
            author="Bob", 
            rating=1,
            context_image_path="fake_path.jpg"
        )
        
        # Verify: Claude WAS called
        self.assertTrue(mock_claude_client.messages.create.called)
        self.assertEqual(result['consulting_notes'], "Context: Owner needs to know...")
        
        # Verify: DeepSeek WAS called
        self.assertTrue(mock_deepseek_client.chat.completions.create.called)
        self.assertEqual(result['vietnamese_summary'], "Khách giận")

if __name__ == '__main__':
    unittest.main()
