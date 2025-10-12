"""
Data Loader for SQLite Database.

Handles loading historical market data from SQLite databases for backtesting.
"""

import logging
import sqlite3
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class SQLiteDataLoader:
    """
    Loader for historical market data from SQLite databases.

    Supports:
    - Single and multiple database files
    - Auto-detection of symbols
    - Data validation and cleaning
    - Multiple date formats
    """

    # Common table names to try
    COMMON_TABLE_NAMES = [
        'market_data',
        'ohlcv',
        'historical_data',
        'stock_data',
        'quotes'
    ]

    # Expected column mappings (database_column: standard_column)
    COLUMN_MAPPINGS = {
        # Timestamp columns
        'timestamp': 'timestamp',
        'datetime': 'timestamp',
        'date': 'timestamp',
        'time': 'timestamp',

        # Symbol columns
        'symbol': 'symbol',
        'ticker': 'symbol',
        'stock': 'symbol',
        'instrument': 'symbol',

        # Price columns
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'volume': 'volume',

        # Alternative names
        'o': 'open',
        'h': 'high',
        'l': 'low',
        'c': 'close',
        'v': 'volume',
    }

    def __init__(self):
        """Initialize the data loader."""
        self.cached_schemas: Dict[str, Dict] = {}
        logger.info("Initialized SQLiteDataLoader")

    def load_from_database(
            self,
            db_path: str,
            symbol: str,
            table_name: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """
        Load data for a symbol from SQLite database.

        Args:
            db_path: Path to SQLite database file
            symbol: Symbol to load
            table_name: Specific table name (auto-detect if None)
            start_date: Start date filter (YYYY-MM-DD)
            end_date: End date filter (YYYY-MM-DD)

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        db_path = Path(db_path)

        if not db_path.exists():
            logger.error(f"Database not found: {db_path}")
            return None

        try:
            # Connect to database
            conn = sqlite3.connect(str(db_path))

            # Find table name if not specified
            if table_name is None:
                table_name = self._detect_table_name(conn)
                if table_name is None:
                    logger.error(f"Could not detect table name in {db_path}")
                    return None

            # Get schema info
            schema = self._get_schema(conn, table_name)
            if not schema:
                logger.error(f"Could not read schema for table {table_name}")
                return None

            # Map columns
            column_map = self._map_columns(schema)

            # Build query
            query = self._build_query(
                table_name, column_map, symbol, start_date, end_date
            )

            # Load data
            df = pd.read_sql_query(query, conn)
            conn.close()

            if df.empty:
                logger.debug(f"No data found for {symbol} in {db_path}")
                return None

            # Standardize column names
            df = self._standardize_columns(df, column_map)

            # Validate and clean
            df = self._validate_and_clean(df)

            logger.info(f"Loaded {len(df)} records for {symbol} from {db_path}")
            return df

        except Exception as e:
            logger.error(f"Error loading data from {db_path}: {e}")
            return None

    def _detect_table_name(self, conn: sqlite3.Connection) -> Optional[str]:
        """Auto-detect table name in database."""
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        # Try common table names first
        for common_name in self.COMMON_TABLE_NAMES:
            if common_name in tables:
                logger.debug(f"Detected table: {common_name}")
                return common_name

        # If no match, use first table
        if tables:
            logger.debug(f"Using first table: {tables[0]}")
            return tables[0]

        return None

    def _get_schema(self, conn: sqlite3.Connection, table_name: str) -> Optional[Dict]:
        """Get table schema information."""
        try:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()

            schema = {
                col[1].lower(): {  # column name (lowercase)
                    'type': col[2],
                    'notnull': col[3],
                    'pk': col[5]
                }
                for col in columns
            }

            return schema

        except Exception as e:
            logger.error(f"Error getting schema: {e}")
            return None

    def _map_columns(self, schema: Dict) -> Dict[str, str]:
        """
        Map database columns to standard columns.

        Args:
            schema: Database schema dict

        Returns:
            Dict mapping database_column -> standard_column
        """
        column_map = {}

        for db_col in schema.keys():
            # Check if column name matches any mapping
            for db_variant, standard_name in self.COLUMN_MAPPINGS.items():
                if db_col == db_variant or db_col.endswith(f'_{db_variant}'):
                    column_map[db_col] = standard_name
                    break

        return column_map

    def _build_query(
            self,
            table_name: str,
            column_map: Dict[str, str],
            symbol: str,
            start_date: Optional[str],
            end_date: Optional[str]
    ) -> str:
        """Build SQL query to load data."""
        # Find symbol column
        symbol_col = None
        for db_col, std_col in column_map.items():
            if std_col == 'symbol':
                symbol_col = db_col
                break

        # Find timestamp column
        timestamp_col = None
        for db_col, std_col in column_map.items():
            if std_col == 'timestamp':
                timestamp_col = db_col
                break

        # Build SELECT clause
        select_cols = []
        for db_col, std_col in column_map.items():
            select_cols.append(f"{db_col} as {std_col}")

        if not select_cols:
            # Fallback: select all columns
            select_cols = ["*"]

        # Build WHERE clause
        where_clauses = []

        if symbol_col:
            where_clauses.append(f"{symbol_col} = '{symbol}'")

        if timestamp_col and start_date:
            where_clauses.append(f"{timestamp_col} >= '{start_date}'")

        if timestamp_col and end_date:
            where_clauses.append(f"{timestamp_col} <= '{end_date}'")

        # Construct query
        query = f"SELECT {', '.join(select_cols)} FROM {table_name}"

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        if timestamp_col:
            query += f" ORDER BY {timestamp_col}"

        logger.debug(f"Query: {query}")
        return query

    def _standardize_columns(self, df: pd.DataFrame, column_map: Dict) -> pd.DataFrame:
        """Ensure DataFrame has standard column names."""
        # Required columns
        required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

        # Check what we have
        missing = [col for col in required if col not in df.columns]

        if missing:
            logger.warning(f"Missing columns: {missing}")
            # Try to infer from column names
            for col in missing:
                # Look for similar column names
                for df_col in df.columns:
                    if col in df_col.lower():
                        df[col] = df[df_col]
                        break

        # Ensure timestamp is datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Select only required columns
        available_cols = [col for col in required if col in df.columns]
        df = df[available_cols].copy()

        return df

    def _validate_and_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and clean the data."""
        if df.empty:
            return df

        original_len = len(df)

        # Remove rows with missing OHLC data
        required_cols = ['open', 'high', 'low', 'close']
        df = df.dropna(subset=[col for col in required_cols if col in df.columns])

        # Remove rows with zero or negative prices
        for col in required_cols:
            if col in df.columns:
                df = df[df[col] > 0]

        # Validate OHLC relationships
        if all(col in df.columns for col in required_cols):
            # High should be >= Low
            df = df[df['high'] >= df['low']]

            # High should be >= Open and Close
            df = df[df['high'] >= df['open']]
            df = df[df['high'] >= df['close']]

            # Low should be <= Open and Close
            df = df[df['low'] <= df['open']]
            df = df[df['low'] <= df['close']]

        # Sort by timestamp
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp')

        # Remove duplicates
        df = df.drop_duplicates(subset=['timestamp'], keep='first')

        # Reset index
        df = df.reset_index(drop=True)

        removed = original_len - len(df)
        if removed > 0:
            logger.debug(f"Cleaned data: removed {removed} invalid records")

        return df

    def auto_detect_symbols(
            self,
            db_paths: List[str],
            min_records: int = 100
    ) -> List[str]:
        """
        Auto-detect available symbols across multiple databases.

        Args:
            db_paths: List of database file paths
            min_records: Minimum records required per symbol

        Returns:
            List of available symbols
        """
        all_symbols = set()

        for db_path in db_paths:
            symbols = self._get_symbols_from_db(db_path, min_records)
            all_symbols.update(symbols)

        logger.info(f"Detected {len(all_symbols)} symbols across {len(db_paths)} databases")
        return sorted(list(all_symbols))

    def _get_symbols_from_db(self, db_path: str, min_records: int) -> List[str]:
        """Get list of symbols from a database."""
        db_path = Path(db_path)

        if not db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(db_path))

            # Detect table
            table_name = self._detect_table_name(conn)
            if not table_name:
                return []

            # Get schema
            schema = self._get_schema(conn, table_name)
            if not schema:
                return []

            # Find symbol column
            column_map = self._map_columns(schema)
            symbol_col = None
            for db_col, std_col in column_map.items():
                if std_col == 'symbol':
                    symbol_col = db_col
                    break

            if not symbol_col:
                logger.debug(f"No symbol column found in {db_path}")
                return []

            # Query symbols with record counts
            query = f"""
                SELECT {symbol_col}, COUNT(*) as count
                FROM {table_name}
                GROUP BY {symbol_col}
                HAVING count >= {min_records}
            """

            df = pd.read_sql_query(query, conn)
            conn.close()

            symbols = df[symbol_col].tolist()
            logger.debug(f"Found {len(symbols)} symbols in {db_path}")

            return symbols

        except Exception as e:
            logger.error(f"Error detecting symbols from {db_path}: {e}")
            return []

    def combine_multi_database_data(
            self,
            symbol: str,
            db_paths: List[str]
    ) -> Optional[pd.DataFrame]:
        """
        Combine data for a symbol from multiple databases.

        Args:
            symbol: Symbol to load
            db_paths: List of database paths

        Returns:
            Combined DataFrame
        """
        dfs = []

        for db_path in db_paths:
            df = self.load_from_database(db_path, symbol)
            if df is not None:
                dfs.append(df)

        if not dfs:
            return None

        # Combine and sort
        combined_df = pd.concat(dfs, ignore_index=True)
        combined_df = combined_df.sort_values('timestamp')
        combined_df = combined_df.drop_duplicates(subset=['timestamp'], keep='first')
        combined_df = combined_df.reset_index(drop=True)

        logger.info(f"Combined {len(combined_df)} records for {symbol} from {len(dfs)} databases")
        return combined_df


# Convenience function
def load_data(db_path: str, symbol: str) -> Optional[pd.DataFrame]:
    """
    Convenience function to load data.

    Args:
        db_path: Database file path
        symbol: Symbol to load

    Returns:
        DataFrame with OHLCV data
    """
    loader = SQLiteDataLoader()
    return loader.load_from_database(db_path, symbol)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    loader = SQLiteDataLoader()

    # Example: Load data for a symbol
    # df = loader.load_from_database("data/market_data.db", "NSE:RELIANCE-EQ")
    # if df is not None:
    #     print(df.head())
    #     print(f"\nLoaded {len(df)} records")

    print("SQLite Data Loader initialized")
    print("Use load_from_database() to load market data")