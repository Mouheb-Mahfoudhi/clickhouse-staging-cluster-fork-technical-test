#!/usr/bin/env python3
import requests
import getpass
import sys
import re

CH01 = "http://localhost:8123"
CH02 = "http://localhost:8124"

DATABASES = [
    "reporting_shop1_green",
    "reporting_shop2_green",
    "reporting_shop3_green",
    "reporting_shop4_green",
]

class QueryError(Exception):
    def __init__(self, sql, response_text):
        self.sql = sql
        self.response_text = response_text
        match = re.search(r"Code:\s*(\d+)", response_text)
        self.code = int(match.group(1)) if match else None
        super().__init__(response_text)

def query(host, sql, user, password):
    resp = requests.post(host, params={"user": user, "password": password}, data=sql.encode())
    if resp.status_code != 200:
        raise QueryError(sql, resp.text)
    return resp.text.strip()

def main():
    user = input("ClickHouse username [default]: ").strip() or "default"
    password = getpass.getpass("ClickHouse password: ")

    def q1(sql): return query(CH01, sql, user, password)
    def q2(sql): return query(CH02, sql, user, password)

    total = 0
    for db in DATABASES:
        print(f"\n━━━ {db} ━━━")
        tables = q2(
            f"SELECT name FROM system.tables "
            f"WHERE database = '{db}' AND engine LIKE 'Replicated%'"
        ).splitlines()

        for table in tables:
            try:
                is_readonly = q2(
                    f"SELECT is_readonly FROM system.replicas "
                    f"WHERE database = '{db}' AND table = '{table}'"
                )
            except QueryError as err:
                print(f"\n Failed while checking replica state for `{db}`.`{table}`:")
                print(err.response_text)
                sys.exit(1)

            if is_readonly == "1":
                print(f"  → RESTORE {table}", end="  ", flush=True)
                try:
                    q2(f"SYSTEM RESTORE REPLICA `{db}`.`{table}`")
                    print("-ok")
                    total += 1
                except QueryError as err:
                    if err.code == 36 and "Replica must be readonly" in err.response_text:
                        print(" skipped (replica switched to writable)")
                        continue
                    print(f"\n Failed restoring `{db}`.`{table}`:")
                    print(err.response_text)
                    sys.exit(1)
            else:
                print(f"  → SKIP {table} (replica is writable, no RESTORE needed)")

    print(f"\n Restored {total} replicas. Checking status...\n")

    status = q1(
        "SELECT database, table, is_readonly, active_replicas, total_replicas "
        "FROM system.replicas "
        "ORDER BY database, table "
        "FORMAT PrettyCompact"
    )
    print(status)

if __name__ == "__main__":
    main()
