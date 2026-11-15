"""Flask entrypoint for Vercel; reuse the tested application handlers."""
import io
import logging
import os
from flask import Flask, Response, request
from werkzeug.exceptions import HTTPException
import server

app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 4_000_000


@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(Exception)
def error_response(error):
    if isinstance(error, HTTPException):
        return {'error': error.description}, error.code
    logging.exception('Souvenue request failed')
    return {'error': 'The service is temporarily unavailable. Please try again.'}, 503


@app.route('/', defaults={'path': ''}, methods=['GET', 'POST'])
@app.route('/<path:path>', methods=['GET', 'POST'])
def dispatch(path):
    if os.environ.get('VERCEL') and not os.environ.get('DATABASE_URL'):
        return {'error': 'DATABASE_URL must be configured before deployment.'}, 503
    if path == 'api/health':
        with server.db() as connection:
            connection.execute('SELECT id FROM users LIMIT 1').fetchone()
        return {'ok': True, 'database': 'postgres' if os.environ.get('DATABASE_URL') else 'sqlite'}
    handler = object.__new__(server.Handler)
    handler.path = request.full_path.rstrip('?')
    handler.headers = dict(request.headers)
    handler.headers['Host'] = request.host
    handler.headers['Content-Length'] = str(request.content_length or 0)
    handler.rfile = io.BytesIO(request.get_data())
    handler.wfile = io.BytesIO()
    status, headers = [200], []
    handler.send_response = lambda code: status.__setitem__(0, code)
    handler.send_header = lambda key, value: headers.append((key, value))
    handler.end_headers = lambda: None
    getattr(handler, 'do_' + ('GET' if request.method == 'HEAD' else request.method))()
    return Response(handler.wfile.getvalue(), status=status[0], headers=headers)
