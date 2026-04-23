from database import init_db, get_db_connection
from services.phase1_onboarding import handle_onboarding_step, synthesize_profile
from services.phase2_opportunities import search_opportunities


if __name__ == '__main__':
    init_db()
    print('DB initialized')

    handle_onboarding_step(1, 1, 'Marketing roles, content, remote')
    handle_onboarding_step(1, 2, 'BBA in Marketing, grad 2024')
    handle_onboarding_step(1, 3, 'Built campaigns, used Google Analytics, SEO')
    handle_onboarding_step(1, 4, 'John Doe\njohn@example.com\n+1 555-123-4567\ngithub.com/johndoe')

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id=1').fetchone()
    print('User row:')
    print(dict(user) if user else 'No user')
    conn.close()

    print('\nSynthesize profile (LLM may be called):')
    try:
        profile = synthesize_profile(1)
        print(profile)
    except Exception as e:
        print('Synthesis error:', e)

    print('\nSearch opportunities (uses TAVILY if configured):')
    try:
        opps = search_opportunities(1)
        print(opps)
    except Exception as e:
        print('Search error:', e)
