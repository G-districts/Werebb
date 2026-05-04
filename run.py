#!/usr/bin/env python3
"""
WHERE BAZINC — Community Tracking & Alert Network
Run this file to start the server.
"""
from app import app, init_db

if __name__ == "__main__":
    print("""
  ██╗    ██╗██╗  ██╗███████╗██████╗ ███████╗
  ██║    ██║██║  ██║██╔════╝██╔══██╗██╔════╝
  ██║ █╗ ██║███████║█████╗  ██████╔╝█████╗  
  ██║███╗██║██╔══██║██╔══╝  ██╔══██╗██╔══╝  
  ╚███╔███╔╝██║  ██║███████╗██║  ██║███████╗
   ╚══╝╚══╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝
  BAZINC // COMMUNITY ALERT NETWORK
  ═══════════════════════════════════════════
    """)
    init_db()
    print("  ✓ Database initialized")
    print("  ✓ Server starting on http://localhost:5000")
    print("  → Admin login: phone=0000000000  password=admin123")
    print("  → Change admin credentials after first login!\n")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
