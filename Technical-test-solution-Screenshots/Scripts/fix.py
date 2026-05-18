#!/usr/bin/env python3
import requests
import getpass
import sys

CH01 = "http://localhost:8123"
CH02 = "http://localhost:8124"

DATABASES = [
    "reporting_shop1_green",
    "reporting_shop2_green",
    "reporting_shop3_green",
    "reporting_shop4_green",
]

def query(host, sql, user, password):
    resp = requests.post(
        host,
        params={"user": user, "password": password},
        data=sql.encode("utf-8"),
    )
    if resp.status_code != 200:
        print(f"\n Query failed:\n{sql}\n\nError:\n{resp.text}")
        sys.exit(1)
    return resp.text.strip()

def main():
    user = input("ClickHouse username [default]: ").strip() or "default"
    password = getpass.getpass("ClickHouse password: ")

    def q1(sql):
        return query(CH01, sql, user, password)
    def q2(sql):
        return query(CH02, sql, user, password)

    print("\n Checking connections.")
    q1("SELECT 1")
    q2("SELECT 1")
    print("ch01 reachable")
    print("ch02 reachable")

    total = 0
    for db in DATABASES:
        print(f"\n━━━ {db} ━━━")

        result = q2(
            f"SELECT name FROM system.tables "
            f"WHERE database = '{db}' AND engine LIKE 'Replicated%'"
        )
        tables = [t for t in result.splitlines() if t]

        if not tables:
            print("   (no replicated tables found)")
            continue

        for table in tables:
            print(f"  → {table}", end="  ", flush=True)

            uuid = q2(
                f"SELECT uuid FROM system.tables "
                f"WHERE database = '{db}' AND name = '{table}'"
            )

            ddl = q2(f"SHOW CREATE TABLE `{db}`.`{table}` FORMAT TSVRaw")

            #  SHOW CREATE TABLE returns no backticks
            ddl = ddl.replace(
                f"CREATE TABLE {db}.{table}",
                f"CREATE TABLE {db}.{table} UUID '{uuid}'",
                1,
            )

            # Safety check if UUID still not in DDL then something is wrong
            if uuid not in ddl:
                print(f"\n UUID injection failed for {db}.{table}")
                print(f"   DDL first line: {ddl.splitlines()[0]}")
                sys.exit(1)

            q1(f"DROP TABLE IF EXISTS `{db}`.`{table}` SYNC")
            q1(ddl)

            print(f"-ok:({uuid})")
            total += 1

    print(f"\n Done - {total} tables recreated.\n")

    status = q1(
        "SELECT database, table, is_readonly, active_replicas, "
        "total_replicas, absolute_delay "
        "FROM system.replicas "
        "ORDER BY database, table "
        "FORMAT PrettyCompact"
    )
    print(status)

if __name__ == "__main__":
    main()