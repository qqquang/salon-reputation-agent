
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.db.supabase_client import db

def cleanup():
    client = db.get_client()
    
    print("Starting cleanup...")
    
    # 1. Delete rows with "Lỗi dịch thuật."
    res1 = client.table("reviews").delete().eq("vietnamese_summary", "Lỗi dịch thuật.").execute()
    count1 = len(res1.data) if res1.data else 0
    print(f"Deleted {count1} rows with 'Lỗi dịch thuật.'")

    # 2. Delete rows with "Analysis Failed" category
    res2 = client.table("reviews").delete().eq("category", "Analysis Failed").execute()
    count2 = len(res2.data) if res2.data else 0
    print(f"Deleted {count2} rows with 'Analysis Failed'")

    # 3. Delete rows with "Lỗi phân tích (Rate Limit)."
    res3 = client.table("reviews").delete().eq("vietnamese_summary", "Lỗi phân tích (Rate Limit).").execute()
    count3 = len(res3.data) if res3.data else 0
    print(f"Deleted {count3} rows with 'Lỗi phân tích (Rate Limit).'")
    
    total = count1 + count2 + count3
    print(f"\nTotal rows deleted: {total}")

if __name__ == "__main__":
    cleanup()
