from conftest import graphql_request

REGISTER_MUTATION = """
mutation Register($input: RegisterInput!) {
    register(input: $input) {
        accessToken
        refreshToken
        user {
            id
            username
            email
        }
    }
}
"""

LOGIN_MUTATION = """
mutation Login($input: LoginInput!) {
    login(input: $input) {
        accessToken
        refreshToken
        user {
            id
            username
            email
        }
    }
}
"""

REFRESH_MUTATION = """
mutation RefreshToken($refreshToken: String!) {
    refreshToken(refreshToken: $refreshToken) {
        accessToken
        refreshToken
        user {
            id
            username
        }
    }
}
"""

LOGOUT_MUTATION = """
mutation Logout($refreshToken: String!) {
    logout(refreshToken: $refreshToken)
}
"""

CURRENT_USER_QUERY = """
query CurrentUser {
    currentUser {
        id
        username
        email
    }
}
"""


async def test_register_and_current_user_flow(client):
    # Registration
    res = await graphql_request(
        client,
        query=REGISTER_MUTATION,
        variables={"input": {"username": "alice", "email": "alice@example.com", "password": "Password123!"}},
    )
    data = res["data"]["register"]
    access_token = data["accessToken"]
    assert data["user"]["username"] == "alice"

    # Reading currentUser with a token
    me_res = await graphql_request(client, query=CURRENT_USER_QUERY, token=access_token)
    me_data = me_res["data"]["currentUser"]
    assert me_data["username"] == "alice"
    assert me_data["email"] == "alice@example.com"


async def test_register_duplicate_username_or_email(client):
    variables = {"input": {"username": "bob", "email": "bob@example.com", "password": "Password123!"}}
    await graphql_request(client, query=REGISTER_MUTATION, variables=variables)

    # Re-registration
    res = await graphql_request(client, query=REGISTER_MUTATION, variables=variables)
    assert "errors" in res
    assert "Username or email is already taken" in res["errors"][0]["message"]


async def test_login_success_and_failure(client):
    await graphql_request(
        client,
        query=REGISTER_MUTATION,
        variables={"input": {"username": "charlie", "email": "charlie@example.com", "password": "Password123!"}},
    )

    # Incorrect password
    bad_login = await graphql_request(
        client,
        query=LOGIN_MUTATION,
        variables={"input": {"email": "charlie@example.com", "password": "WrongPassword"}},
    )
    assert "Invalid email or password" in bad_login["errors"][0]["message"]

    # Successful login
    good_login = await graphql_request(
        client,
        query=LOGIN_MUTATION,
        variables={"input": {"email": "charlie@example.com", "password": "Password123!"}},
    )
    assert good_login["data"]["login"]["user"]["username"] == "charlie"


async def test_refresh_token_and_logout_flow(client):
    reg_res = await graphql_request(
        client,
        query=REGISTER_MUTATION,
        variables={"input": {"username": "dave", "email": "dave@example.com", "password": "Password123!"}},
    )
    refresh_token = reg_res["data"]["register"]["refreshToken"]

    # Refresh
    ref_res = await graphql_request(client, query=REFRESH_MUTATION, variables={"refreshToken": refresh_token})
    assert ref_res["data"]["refreshToken"]["user"]["username"] == "dave"

    # Logout
    logout_res = await graphql_request(client, query=LOGOUT_MUTATION, variables={"refreshToken": refresh_token})
    assert logout_res["data"]["logout"] is True

    # A repeated refresh after logout will cause an error.
    failed_ref = await graphql_request(client, query=REFRESH_MUTATION, variables={"refreshToken": refresh_token})
    assert "Invalid or expired refresh token" in failed_ref["errors"][0]["message"]


async def test_current_user_anonymous(client):
    res = await graphql_request(client, query=CURRENT_USER_QUERY)
    assert res["data"]["currentUser"] is None
