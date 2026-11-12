
def refresh_camp_statuses(connection):
    cursor = connection.cursor()

    try:
        # 1. Refresh camp statuses
        cursor.execute("""
            UPDATE camps
            SET status = CASE
                WHEN TIMESTAMP(
                    camp_date,
                    COALESCE(start_time, '00:00:00')
                ) > NOW()
                    THEN 'upcoming'

                WHEN TIMESTAMP(
                    camp_date,
                    COALESCE(end_time, '23:59:59')
                ) < NOW()
                    THEN 'completed'

                ELSE 'ongoing'
            END
            WHERE status != 'cancelled'
        """)

        # 2. Mark unattended patients as missed after camp completion
        cursor.execute("""
            UPDATE registrations r
            JOIN camps c ON r.camp_id = c.camp_id
            SET r.status = 'missed'
            WHERE r.status IN ('waiting', 'in_progress')
              AND c.status = 'completed'
              AND TIMESTAMP(
                  c.camp_date,
                  COALESCE(c.end_time, '23:59:59')
              ) < NOW()
              AND NOT EXISTS (
                  SELECT 1
                  FROM health_records hr
                  WHERE hr.registration_id = r.registration_id
              )
        """)

        # 3. Save both updates
        connection.commit()

    finally:
        cursor.close()
