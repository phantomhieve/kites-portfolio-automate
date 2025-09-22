"""
Webhook server for automated Kite Connect OAuth token extraction.

This module provides a simple HTTP server that can catch OAuth redirects
and automatically extract request tokens from the callback URL.
"""

import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any
import queue

logger = logging.getLogger(__name__)


class TokenCaptureHandler(BaseHTTPRequestHandler):
    """HTTP request handler that captures OAuth tokens from redirect URLs."""
    
    def do_GET(self):
        """Handle GET requests and extract request tokens."""
        try:
            # Parse the request URL
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            
            # Look for request_token in query parameters
            request_token = query_params.get('request_token', [None])[0]
            status = query_params.get('status', [None])[0]
            
            if request_token:
                # Store the token in the server's token queue
                self.server.token_queue.put({
                    'request_token': request_token,
                    'status': status,
                    'timestamp': time.time()
                })
                
                # Send success response
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                response_html = f"""
                <html>
                <head><title>Token Captured</title></head>
                <body>
                    <h2>✅ Token Captured Successfully!</h2>
                    <p><strong>Request Token:</strong> {request_token}</p>
                    <p><strong>Status:</strong> {status or 'success'}</p>
                    <p>You can close this window. The automation will continue.</p>
                    <script>setTimeout(() => window.close(), 3000);</script>
                </body>
                </html>
                """
                self.wfile.write(response_html.encode())
                
                logger.info("Captured request token: %s", request_token[:10] + "...")
                
            else:
                # No token found - send error response
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                error_html = """
                <html>
                <head><title>Token Capture Error</title></head>
                <body>
                    <h2>❌ No Token Found</h2>
                    <p>The redirect URL did not contain a request_token parameter.</p>
                    <p>Please check the OAuth flow and try again.</p>
                </body>
                </html>
                """
                self.wfile.write(error_html.encode())
                
                logger.warning("No request_token found in redirect URL: %s", self.path)
                
        except Exception as exc:
            logger.error("Error handling OAuth redirect: %s", exc)
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Server Error</h2></body></html>")
    
    def log_message(self, format, *args):
        """Suppress default HTTP server logging."""
        pass


class TokenWebhookServer:
    """Webhook server for capturing OAuth tokens."""
    
    def __init__(self, host: str = "localhost", port: int = 8080):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.token_queue = queue.Queue()
        
    def start(self) -> str:
        """Start the webhook server and return the callback URL."""
        try:
            self.server = HTTPServer((self.host, self.port), TokenCaptureHandler)
            self.server.token_queue = self.token_queue
            
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            
            callback_url = f"http://{self.host}:{self.port}/callback"
            logger.info("Webhook server started on %s", callback_url)
            return callback_url
            
        except Exception as exc:
            logger.error("Failed to start webhook server: %s", exc)
            raise
    
    def stop(self):
        """Stop the webhook server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Webhook server stopped")
    
    def wait_for_token(self, timeout: int = 300) -> Optional[Dict[str, Any]]:
        """Wait for a token to be captured, with timeout."""
        try:
            token_data = self.token_queue.get(timeout=timeout)
            logger.info("Token captured successfully")
            return token_data
        except queue.Empty:
            logger.warning("Timeout waiting for token capture")
            return None
    
    def get_redirect_url(self, api_key: str) -> str:
        """Generate the Kite Connect login URL with our callback."""
        callback_url = f"http://{self.host}:{self.port}/callback"
        return f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3&redirect_url={callback_url}"


def capture_token_via_webhook(api_key: str, timeout: int = 300) -> Optional[str]:
    """
    Capture a request token via webhook server.
    
    Args:
        api_key: Kite Connect API key
        timeout: Timeout in seconds to wait for token
        
    Returns:
        Request token if captured, None if timeout or error
    """
    server = TokenWebhookServer()
    
    try:
        # Start webhook server
        callback_url = server.start()
        
        # Generate login URL with our callback
        login_url = server.get_redirect_url(api_key)
        
        logger.info("🔗 Open this URL in your browser to login:")
        logger.info("URL: %s", login_url)
        logger.info("⏳ Waiting for OAuth callback (timeout: %d seconds)...", timeout)
        
        # Wait for token capture
        token_data = server.wait_for_token(timeout)
        
        if token_data and token_data.get('request_token'):
            return token_data['request_token']
        else:
            logger.error("Failed to capture request token")
            return None
            
    finally:
        server.stop()
