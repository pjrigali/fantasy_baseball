import os
import pandas as pd
from fantasy_baseball import mlb_processing as mp
from datetime import datetime

def main():
    # User asked for "last year". Assuming 2024.
    target_year = 2024
    print(f"--- Starting Transaction Update for {target_year} ---")
    
    # 1. Load config
    try:
        config = mp.load_config()
        print("Config loaded.")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # 2. Setup League
    try:
        # Initialize with CURRENT year (2025) to ensure successful auth/cookies
        print("Initializing league for 2025 to establish session...")
        league = mp.setup_league(config, year=2025)
        
        # Checking if 2024 is accessible by swapping year
        print(f"Swapping league year to {target_year}...")
        league.year = target_year
        if hasattr(league.espn_request, 'year'):
            league.espn_request.year = target_year
            
        print(f"League initialized: {league}")
    except Exception as e:
        print(f"Error initializing league: {e}")
        return

    # 3. Fetch Transactions
    print("Fetching transactions...")
    try:
        transactions = mp.get_league_transactions(league)
        print(f"Fetched {len(transactions)} transaction records.")
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        return

    # 4. Save to Data Lake
    if transactions:
        try:
            df = pd.DataFrame(transactions)
            
            # Ensure directory exists
            os.makedirs(mp.DATA_PATH, exist_ok=True)
            
            filename = f"transactions_espn_season_{target_year}.csv"
            save_path = os.path.join(mp.DATA_PATH, filename)
            
            df.to_csv(save_path, index=False)
            print(f"Successfully saved data to: {save_path}")
            
            # Preview
            print("\nPreview:")
            print(df.head())
            
        except Exception as e:
            print(f"Error saving data: {e}")
    else:
        print("No transactions found or error in fetching.")

if __name__ == "__main__":
    main()
