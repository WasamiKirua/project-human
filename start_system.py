#!/usr/bin/env python3
"""
Simple startup instructions for the voice assistant system.
"""

def main():
    print("🚀 Voice Assistant Startup Guide")
    print("=" * 50)
    print("\n📋 Required Components (run in separate terminals):")
    print("\n1. STT Component:")
    print("   python stt_component.py")
    print("\n2. LLM Component:")
    print("   python llm_component.py")
    print("\n3. TTS Component:")
    print("   python tts_component.py") 
    print("\n4. GUI (Main Interface):")
    print("   python gui_main.py")
    print("\n✅ Expected Output:")
    print("   Each should show: '[Component] Listening for...'")
    print("   GUI should show: 'Status: Ready 🌸'")
    print("\n🎯 Test Flow:")
    print("   Click '🎤 Start Talking' → Watch console logs → See status changes")
    print("\n🔄 NEW: Continuous Mode:")
    print("   Click '🔄 Enable Continuous Mode' for hands-free conversations!")
    print("   System will auto-restart listening after each AI response")
    print("\n🔧 Troubleshooting:")
    print("   - Ensure Redis is running (port 6379, password 'rhost21')")
    print("   - Check that all components stay running (don't exit)")
    print("   - Look for '[State] Loaded rules' message")
    print("   - Use '🛑 Emergency Stop' if continuous mode gets stuck")

if __name__ == "__main__":
    main()
