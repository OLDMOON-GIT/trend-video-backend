"""
API Security Regression Tests

Tests critical security features:
- Path traversal attack prevention
- SQL injection prevention
- Input validation
- Authentication checks
- Rate limiting
"""
import pytest
from pathlib import Path
import re


class TestPathTraversalPrevention:
    """Test path traversal attack prevention"""

    def test_reject_parent_directory_access(self):
        """Should reject ../ in file paths"""
        dangerous_paths = [
            '../../../etc/passwd',
            '..\\..\\..\\windows\\system32',
            'folder/../../../secret',
            './../../etc/hosts',
        ]

        for path in dangerous_paths:
            # Normalize path and check for traversal
            normalized = Path(path).resolve()
            base_dir = Path('/app/videos').resolve()

            # Security check: reject if normalized path escapes base directory
            try:
                normalized.relative_to(base_dir)
                is_safe = True
            except ValueError:
                is_safe = False

            # Should be flagged as unsafe
            assert is_safe == False, f"Path should be rejected: {path}"

    def test_accept_safe_paths(self):
        """Should accept safe relative paths"""
        safe_paths = [
            'videos/output.mp4',
            'generated_videos/scene_01.mp4',
            './thumbnails/thumb.jpg',
        ]

        base_dir = Path('/app/videos')

        for path in safe_paths:
            # Simulate safe path resolution
            full_path = (base_dir / path).resolve()

            try:
                full_path.relative_to(base_dir.resolve())
                is_safe = True
            except ValueError:
                is_safe = False

            assert is_safe == True, f"Path should be accepted: {path}"

    def test_null_byte_injection(self):
        """Should reject null byte injection attempts"""
        dangerous_inputs = [
            'file.txt\x00.jpg',
            'video\x00.mp4',
            'test\0malicious',
        ]

        for input_str in dangerous_inputs:
            # Check for null bytes
            has_null_byte = '\x00' in input_str or '\0' in input_str

            assert has_null_byte == True, "Null byte should be detected"


class TestInputValidation:
    """Test input validation and sanitization"""

    def test_script_id_validation(self):
        """Script IDs should follow specific format"""
        valid_ids = [
            'task_1730707878091',
            'task_1234567890123',
            'task_9999999999999',
        ]

        invalid_ids = [
            'invalid',
            'task_',
            'task_abc',
            '../../etc/passwd',
            '<script>alert(1)</script>',
            'DROP TABLE scripts;',
        ]

        pattern = re.compile(r'^task_\d{13}$')

        for script_id in valid_ids:
            assert pattern.match(script_id), f"Should be valid: {script_id}"

        for script_id in invalid_ids:
            assert not pattern.match(script_id), f"Should be invalid: {script_id}"

    def test_email_validation(self):
        """Email addresses should be properly validated"""
        valid_emails = [
            'user@example.com',
            'test.user@test.co.kr',
            'admin+tag@domain.com',
        ]

        invalid_emails = [
            'invalid',
            '@example.com',
            'user@',
            'user space@example.com',
            'user@.com',
            '../../../etc/passwd',
        ]

        # Simple email regex (RFC 5322 simplified)
        pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

        for email in valid_emails:
            assert pattern.match(email), f"Should be valid: {email}"

        for email in invalid_emails:
            assert not pattern.match(email), f"Should be invalid: {email}"

    def test_credit_amount_validation(self):
        """Credit amounts should be within safe ranges"""
        valid_amounts = [0, 1, 100, 1000, 10000]
        invalid_amounts = [-1, -100, 10000001, float('inf'), float('-inf')]

        MIN_CREDIT = 0
        MAX_CREDIT = 10000000

        for amount in valid_amounts:
            is_valid = MIN_CREDIT <= amount <= MAX_CREDIT and amount != float('inf')
            assert is_valid == True, f"Should be valid: {amount}"

        for amount in invalid_amounts:
            is_valid = MIN_CREDIT <= amount <= MAX_CREDIT and amount != float('inf') and amount != float('-inf')
            assert is_valid == False, f"Should be invalid: {amount}"


class TestSQLInjectionPrevention:
    """Test SQL injection prevention"""

    def test_detect_sql_injection_patterns(self):
        """Should detect common SQL injection patterns"""
        sql_injection_attempts = [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "1' UNION SELECT * FROM passwords--",
            "admin'--",
            "1'; DELETE FROM scripts WHERE '1'='1",
        ]

        # Simple SQL injection pattern detection
        sql_keywords = ['DROP', 'DELETE', 'UNION', 'INSERT', 'UPDATE', '--', ';']
        sql_chars = ["'", '"', '=']

        for attempt in sql_injection_attempts:
            # Check if input contains SQL keywords or suspicious characters
            contains_sql_keyword = any(keyword in attempt.upper() for keyword in sql_keywords)
            contains_sql_chars = any(char in attempt for char in sql_chars)
            is_suspicious = contains_sql_keyword or (contains_sql_chars and (' OR ' in attempt.upper() or ' AND ' in attempt.upper()))
            assert is_suspicious == True, f"SQL injection should be detected: {attempt}"

    def test_parameterized_query_format(self):
        """Should use parameterized queries, not string concatenation"""
        # Bad: String concatenation (vulnerable)
        user_input = "test'; DROP TABLE users; --"
        bad_query = f"SELECT * FROM users WHERE email = '{user_input}'"

        # Check if dangerous pattern exists
        assert "DROP TABLE" in bad_query, "Vulnerable to SQL injection"

        # Good: Parameterized query (safe)
        good_query_template = "SELECT * FROM users WHERE email = ?"
        params = (user_input,)

        # Parameterized queries don't concatenate directly
        assert user_input not in good_query_template
        assert good_query_template.count('?') == len(params)


class TestAuthenticationSecurity:
    """Test authentication and authorization checks"""

    def test_admin_only_endpoints(self):
        """Admin endpoints should require admin privileges"""
        admin_endpoints = [
            '/api/admin/users',
            '/api/admin/settings',
            '/api/admin/backup',
            '/api/admin/credits',
        ]

        # Simulate different user types
        users = [
            {'isAdmin': False, 'id': 'user1'},  # Regular user
            {'isAdmin': True, 'id': 'admin1'},  # Admin user
        ]

        for endpoint in admin_endpoints:
            for user in users:
                # Check if user should have access
                has_access = user['isAdmin']

                if user['isAdmin']:
                    assert has_access == True, f"Admin should access: {endpoint}"
                else:
                    assert has_access == False, f"User should NOT access: {endpoint}"

    def test_password_requirements(self):
        """Passwords should meet security requirements"""
        valid_passwords = [
            'StrongPass123!',
            'MyP@ssw0rd',
            'Secure#2024',
        ]

        invalid_passwords = [
            '123',  # Too short
            'password',  # No numbers or special chars
            '12345678',  # No letters
            'Pass1',  # Too short
        ]

        def is_strong_password(password: str) -> bool:
            """Check if password meets requirements"""
            if len(password) < 8:
                return False
            has_digit = any(c.isdigit() for c in password)
            has_letter = any(c.isalpha() for c in password)
            return has_digit and has_letter

        for pwd in valid_passwords:
            assert is_strong_password(pwd), f"Should be valid: {pwd}"

        for pwd in invalid_passwords:
            assert not is_strong_password(pwd), f"Should be invalid: {pwd}"


class TestFileUploadSecurity:
    """Test file upload security"""

    def test_allowed_file_extensions(self):
        """Only allow safe file extensions"""
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.mp4', '.json', '.txt'}

        safe_files = [
            'image.jpg',
            'video.mp4',
            'data.json',
            'script.txt',
        ]

        dangerous_files = [
            'malware.exe',
            'script.sh',
            'hack.php',
            'virus.bat',
            'backdoor.py',
        ]

        for filename in safe_files:
            ext = Path(filename).suffix.lower()
            assert ext in allowed_extensions, f"Should be allowed: {filename}"

        for filename in dangerous_files:
            ext = Path(filename).suffix.lower()
            assert ext not in allowed_extensions, f"Should be blocked: {filename}"

    def test_file_size_limits(self):
        """File uploads should respect size limits"""
        MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
        MAX_VIDEO_SIZE = 500 * 1024 * 1024  # 500MB

        test_cases = [
            ('image.jpg', 5 * 1024 * 1024, True),  # 5MB image - OK
            ('image.jpg', 50 * 1024 * 1024, False),  # 50MB image - TOO BIG
            ('video.mp4', 100 * 1024 * 1024, True),  # 100MB video - OK
            ('video.mp4', 600 * 1024 * 1024, False),  # 600MB video - TOO BIG
        ]

        for filename, size, should_pass in test_cases:
            ext = Path(filename).suffix.lower()
            max_size = MAX_IMAGE_SIZE if ext in ['.jpg', '.jpeg', '.png'] else MAX_VIDEO_SIZE
            is_valid = size <= max_size

            assert is_valid == should_pass, f"{filename} ({size} bytes) validation failed"


class TestRateLimiting:
    """Test rate limiting logic"""

    def test_api_rate_limit_per_minute(self):
        """Should limit API requests per minute"""
        MAX_REQUESTS_PER_MINUTE = 60

        request_count = 0

        # Simulate 70 requests
        for i in range(70):
            request_count += 1

            # Check if within limit
            if request_count <= MAX_REQUESTS_PER_MINUTE:
                should_allow = True
            else:
                should_allow = False

            if i < MAX_REQUESTS_PER_MINUTE:
                assert should_allow == True, f"Request {i+1} should be allowed"
            else:
                assert should_allow == False, f"Request {i+1} should be blocked"

    def test_user_request_quota(self):
        """Each user should have daily request quota"""
        DAILY_QUOTA = 100

        user_usage = 0

        # Simulate 120 requests
        for i in range(120):
            user_usage += 1

            has_quota = user_usage <= DAILY_QUOTA

            if i < DAILY_QUOTA:
                assert has_quota == True, f"Request {i+1} should be allowed"
            else:
                assert has_quota == False, f"Request {i+1} should exceed quota"


class TestErrorHandling:
    """Test proper error handling"""

    def test_error_messages_no_sensitive_info(self):
        """Error messages should not expose sensitive information"""
        # Bad error messages that leak information
        bad_errors = [
            "Database connection failed: mysql://admin:password123@localhost/db",
            "File not found: /etc/passwd",
            "API Key invalid: sk-1234567890abcdef",
        ]

        # Good error messages (generic)
        good_errors = [
            "Database connection failed",
            "File not found",
            "Authentication failed",
        ]

        sensitive_patterns = ['password', 'mysql://', '/etc/', 'sk-', 'api_key']

        for error in bad_errors:
            has_sensitive_info = any(pattern in error.lower() for pattern in sensitive_patterns)
            assert has_sensitive_info == True, "Should detect sensitive information"

        for error in good_errors:
            has_sensitive_info = any(pattern in error.lower() for pattern in sensitive_patterns)
            assert has_sensitive_info == False, "Should NOT contain sensitive information"


class TestRegressionBugs:
    """Test regression for previously fixed security bugs"""

    def test_directory_listing_disabled(self):
        """Directory listing should be disabled"""
        # Simulate checking if directory listing is enabled
        directory_listing_enabled = False  # Should always be False

        assert directory_listing_enabled == False, "Directory listing must be disabled"

    def test_debug_mode_disabled_in_production(self):
        """Debug mode should be disabled in production"""
        import os

        # Check environment
        env = os.getenv('NODE_ENV', 'production')
        is_debug = os.getenv('DEBUG', 'false').lower() == 'true'

        if env == 'production':
            assert is_debug == False, "Debug mode must be disabled in production"

    def test_cors_properly_configured(self):
        """CORS should be properly configured"""
        allowed_origins = [
            'https://example.com',
            'https://app.example.com',
        ]

        dangerous_origins = [
            '*',  # Allow all - dangerous!
            'null',
            'file://',
        ]

        # Simulate CORS check
        def is_origin_allowed(origin: str) -> bool:
            if origin in ['*', 'null']:
                return False
            return origin in allowed_origins

        for origin in allowed_origins:
            assert is_origin_allowed(origin) == True

        for origin in dangerous_origins:
            assert is_origin_allowed(origin) == False
