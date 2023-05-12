import requests

RUST_TEAM_BASE = "https://team-api.infra.rust-lang.org/v1/"
RETRIES = 5


def fetch_rust_team(repo_label, level):
    repo = repo_label.replace('-', '_')
    url = f"{RUST_TEAM_BASE}permissions/bors.{repo}.{level}.json"
    for retry in range(RETRIES):
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            return resp.json()["github_ids"]
        except requests.exceptions.RequestException as e:
            msg = f"error while fetching {url}"
            msg += f" (try {str(retry)}): {str(e)}"
            print(msg)
            continue
    return []


def verify_level(username, user_id, repo_label, repo_cfg, state, toml_keys,
                 rust_team_level):
    authorized = False
    if repo_cfg.get('auth_collaborators', False):
        authorized = state.get_repo().is_collaborator(username)
    if repo_cfg.get('rust_team', False):
        authorized = user_id in fetch_rust_team(repo_label, rust_team_level)
    if not authorized:
        authorized = username.lower() == state.delegate.lower()
    for toml_key in toml_keys:
        if not authorized:
            authorized = username in repo_cfg.get(toml_key, [])
    return authorized


def verify(username, user_id, repo_label, repo_cfg, state, auth, realtime,
           my_username):
    # The import is inside the function to prevent circular imports: main.py
    # requires auth.py and auth.py requires main.py
    from .main import AuthState

    # In some cases (e.g. non-fully-qualified r+) we recursively talk to
    # ourself via a hidden markdown comment in the message. This is so that
    # when re-synchronizing after shutdown we can parse these comments and
    # still know the SHA for the approval.
    #
    # So comments from self should always be allowed
    if username == my_username:
        return True

    authorized = False
    if auth == AuthState.REVIEWER:
        authorized = verify_level(
            username, user_id, repo_label, repo_cfg, state, ['reviewers'],
            'review',
        )
    elif auth == AuthState.TRY:
        authorized = verify_level(
            username, user_id, repo_label, repo_cfg, state,
            ['reviewers', 'try_users'], 'try',
        )

    if authorized:
        return True
    if realtime:
        reply = f'@{username}: :key: Insufficient privileges: '
        if auth == AuthState.REVIEWER:
            reply += (
                'Collaborator required'
                if repo_cfg.get('auth_collaborators', False)
                else 'Not in reviewers'
            )
        elif auth == AuthState.TRY:
            reply += 'not in try users'
        state.add_comment(reply)
    return False
