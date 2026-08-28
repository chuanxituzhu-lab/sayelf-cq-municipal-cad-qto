from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class DingTalkAuthError(Exception):
    pass


@dataclass(frozen=True)
class DingTalkConfig:
    client_id: str
    client_secret: str
    corp_id: str
    redirect_uri: str
    auth_url: str
    token_url: str
    userinfo_url: str
    real_name_field: str

    @classmethod
    def from_env(cls) -> "DingTalkConfig":
        return cls(
            client_id=os.environ.get("DINGTALK_CLIENT_ID", ""),
            client_secret=os.environ.get("DINGTALK_CLIENT_SECRET", ""),
            corp_id=os.environ.get("DINGTALK_CORP_ID", ""),
            redirect_uri=os.environ.get("DINGTALK_REDIRECT_URI", ""),
            auth_url=os.environ.get("DINGTALK_AUTH_URL", "https://login.dingtalk.com/oauth2/auth"),
            token_url=os.environ.get("DINGTALK_TOKEN_URL", "https://api.dingtalk.com/v1.0/oauth2/userAccessToken"),
            userinfo_url=os.environ.get("DINGTALK_USERINFO_URL", "https://api.dingtalk.com/v1.0/contact/users/me"),
            real_name_field=os.environ.get("DINGTALK_REAL_NAME_ASSERTION_FIELD", "realNameVerified"),
        )

    @property
    def configured(self) -> bool:
        return all((self.client_id, self.client_secret, self.corp_id, self.redirect_uri))

    def authorization_url(self, state: str) -> str:
        if not self.configured:
            raise DingTalkAuthError("钉钉身份配置不完整")
        params = {
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "client_id": self.client_id,
            "scope": "openid",
            "state": state,
            "prompt": "consent",
        }
        return f"{self.auth_url}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> str:
        payload = json.dumps({
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "code": code,
            "grantType": "authorization_code",
        }).encode("utf-8")
        response = self._request(self.token_url, payload=payload, headers={"Content-Type": "application/json"})
        token = response.get("accessToken") or response.get("access_token")
        if not token:
            raise DingTalkAuthError("钉钉未返回用户访问令牌")
        return token

    def fetch_userinfo(self, access_token: str) -> dict:
        response = self._request(self.userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
        user_id = response.get("unionId") or response.get("union_id") or response.get("openId") or response.get("open_id") or response.get("userId") or response.get("userid")
        if not user_id:
            raise DingTalkAuthError("钉钉用户信息缺少稳定用户 ID")
        real_name_value = response.get(self.real_name_field)
        return {
            "user_id": str(user_id),
            "user_name": response.get("nick") or response.get("name") or response.get("userName") or "钉钉成员",
            "corp_id": response.get("corpId") or response.get("corp_id") or self.corp_id,
            "active": response.get("active", True) is not False,
            "real_name_verified": real_name_value is True or str(real_name_value).lower() in {"true", "1", "yes", "是"},
            "raw_userinfo": response,
        }

    @staticmethod
    def _request(url: str, payload: bytes | None = None, headers: dict | None = None) -> dict:
        request = urllib.request.Request(url, data=payload, headers=headers or {}, method="POST" if payload else "GET")
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise DingTalkAuthError(f"钉钉身份服务请求失败：{exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DingTalkAuthError("钉钉身份服务返回内容不是有效 JSON") from exc
        if not isinstance(data, dict):
            raise DingTalkAuthError("钉钉身份服务返回格式不正确")
        return data
