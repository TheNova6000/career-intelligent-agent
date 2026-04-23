from database import get_db_connection


def dedupe():
    conn = get_db_connection()
    cursor = conn.execute('SELECT user_id, job_id, COUNT(*) as cnt FROM opportunities GROUP BY user_id, job_id HAVING cnt > 1')
    rows = cursor.fetchall()

    if not rows:
        print('No duplicate opportunities found.')
        conn.close()
        return

    for r in rows:
        user_id = r['user_id']
        job_id = r['job_id']
        keep_row = conn.execute('SELECT id FROM opportunities WHERE user_id=? AND job_id=? ORDER BY created_at DESC LIMIT 1', (user_id, job_id)).fetchone()
        if not keep_row:
            continue
        keep_id = keep_row['id']
        deleted = conn.execute('DELETE FROM opportunities WHERE user_id=? AND job_id=? AND id != ?', (user_id, job_id, keep_id))
        conn.commit()
        print(f'Deduped user_id={user_id} job_id={job_id}, kept id={keep_id}')

    conn.close()


if __name__ == '__main__':
    dedupe()
