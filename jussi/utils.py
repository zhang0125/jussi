# -*- coding: utf-8 -*-
import functools
import time
import websockets
from collections import OrderedDict
from collections import namedtuple




from jussi.cache import jsonrpc_cache_key

# decorators
def apply_single_or_batch(func):
    """Decorate func to apply func to single or batch jsonrpc_requests

    Args:
        func:

    Returns:
        decorated_function
    """

    @functools.wraps(func)
    def wrapper(jsonrpc_request):
        if isinstance(jsonrpc_request, list):
            jsonrpc_request = list(map(func, jsonrpc_request))
        else:
            jsonrpc_request = func(jsonrpc_request)
        return jsonrpc_request

    return wrapper



def websocket_conn(func):
    """Decorate func to make sure func has an open websocket client

    Args:
        func:

    Returns:

    """
    @functools.wraps(func)
    async def wrapper(app, jussi, jsonrpc_request):
        ws = app.config.websocket_client
        if ws and ws.open:
            # everything ok, noop
            pass
        else:
            ws = await websockets.connect(**app.config.websocket_kwargs)
            app.config.websocket_client = ws
        return await func(app, jussi, jsonrpc_request)
    return wrapper


def return_bytes(func):
    """Decorate func to make sure func has an open websocket client

    Args:
        func:

    Returns:

    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        if isinstance(result, str):
            result = result.encode()
        return result
    return wrapper



def generate_int_id():
    return int(time.time() * 1000000)


@apply_single_or_batch
def replace_jsonrpc_id(single_jsonrpc_request):
    try:
        single_jsonrpc_request['id'] = int(single_jsonrpc_request['id'])
    except ValueError:
        single_jsonrpc_request['id'] = generate_int_id()
    return single_jsonrpc_request


@apply_single_or_batch
def replace_jsonrpc_version(single_jsonrpc_request):
    single_jsonrpc_request['jsonrpc'] = '2.0'
    return single_jsonrpc_request


@apply_single_or_batch
def strip_steemd_method_namespace(single_jsonrpc_request):
    if single_jsonrpc_request['method'].startswith('steemd.'):
        single_jsonrpc_request = strip_namespace(single_jsonrpc_request,
                                                 'steemd')
    return single_jsonrpc_request


@apply_single_or_batch
def sort_request(single_jsonrpc_request):
    params = single_jsonrpc_request.get('params')
    if isinstance(params, list):
        single_jsonrpc_request['params'] = sorted(params)
    elif isinstance(params, dict):
        single_jsonrpc_request['params'] = OrderedDict(
            sorted(single_jsonrpc_request['params']))
    return OrderedDict(sorted(single_jsonrpc_request.items()))


def strip_namespace(request, namespace):
    request['method'] = request['method'].strip('%s.' % namespace)
    return request


def parse_namespaced_method(namespaced_method, default_namespace='steemd'):
    try:
        namespace, method = namespaced_method.split('.')
    except ValueError:
        namespace, method = default_namespace, namespaced_method
    return namespace, method


async def get_upstream(sanic_http_request, jsonrpc_request):
    app = sanic_http_request.app
    jsonrpc_method = jsonrpc_request['method']
    _, upstream = app.config.upstreams.longest_prefix(jsonrpc_method)

    # get default values if no specific values found
    if upstream is None:
        _, upstream = app.config.upstreams.longest_prefix('')

    return upstream['url'], upstream['ttl']


JussiAttributes = namedtuple(
    'JussiAttributes', ['key', 'upstream_url', 'ttl', 'cacheable', 'is_ws'])


async def jussi_attrs(sanic_http_request):
    jsonrpc_requests = sanic_http_request.json
    app = sanic_http_request.app

    if isinstance(jsonrpc_requests, list):
        results = []
        for r in jsonrpc_requests:
            key = jsonrpc_cache_key(r)
            url, ttl = await get_upstream(sanic_http_request, r)
            cacheable = ttl > app.config.cache_config['no_cache_ttl']
            is_ws = url.startswith('ws')
            results.append(
                JussiAttributes(
                    key=key,
                    upstream_url=url,
                    ttl=ttl,
                    cacheable=cacheable,
                    is_ws=is_ws))
        sanic_http_request['jussi'] = results
        sanic_http_request['jussi_is_batch'] = True
    else:
        key = jsonrpc_cache_key(jsonrpc_requests)
        url, ttl = await get_upstream(sanic_http_request, jsonrpc_requests)
        cacheable = ttl > app.config.cache_config['no_cache_ttl']
        is_ws = url.startswith('ws')
        sanic_http_request['jussi'] = JussiAttributes(
            key=key,
            upstream_url=url,
            ttl=ttl,
            cacheable=cacheable,
            is_ws=is_ws)
        sanic_http_request['jussi_is_batch'] = False

    return sanic_http_request