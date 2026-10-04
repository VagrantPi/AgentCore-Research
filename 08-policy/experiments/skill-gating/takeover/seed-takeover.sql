-- WP2 #8 測試資料：要先匯 HephAgora 的 scripts/wp2/seed.sql。冪等。
--   com.wp2.login-web 要買；只有 userB 買
--   binding：http → 開發機上的 browser_skill.py（容器內用 host.docker.internal 連回開發機）
--   timeout_ms 300000：接手要等使用者登入（browser_skill.py 最多等 240 秒）

INSERT INTO services (service_id, version, kind, status, owner, manifest) VALUES
('com.wp2.login-web', '1.0.0', 'tool', 'published', 'wp2', $json$
{
  "id": "com.wp2.login-web", "version": "1.0.0", "type": "tool",
  "display_name": "網站登入", "description": "登入需要帳號的網站並回報登入結果（login）",
  "categories": ["login", "登入", "browser"], "publisher": { "id": "wp2", "name": "WP2" },
  "billing": { "model": "subscription" },
  "capabilities": [{
    "name": "login_and_check",
    "description": "Use this when 使用者要登入測試網站並確認登入結果。需要時會請使用者在手機上接手瀏覽器登入。",
    "permissions": [], "visibility": ["model"], "session": "none",
    "invocation": {
      "mode": "atomic",
      "mcp": { "input_schema": { "type": "object", "properties": {} } },
      "mcp_server": {
        "type": "http",
        "url": "http://host.docker.internal:13200/mcp",
        "tool": "login_and_check",
        "timeout_ms": 300000
      }
    }
  }]
}
$json$::jsonb)
ON CONFLICT (service_id) DO UPDATE SET manifest = EXCLUDED.manifest, status = 'published', embedding = NULL;

INSERT INTO skill_products (service_id, max_calls_per_hour) VALUES ('com.wp2.login-web', NULL)
ON CONFLICT (service_id) DO UPDATE SET max_calls_per_hour = EXCLUDED.max_calls_per_hour;

INSERT INTO skill_entitlements (consumer_id, external_user_id, service_id) VALUES
('wp2-test', 'userB', 'com.wp2.login-web')
ON CONFLICT DO NOTHING;
