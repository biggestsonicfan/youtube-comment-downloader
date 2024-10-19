from __future__ import print_function

import json
import re
import time

import dateparser
import requests

YOUTUBE_VIDEO_URL = 'https://www.youtube.com/watch?v={youtube_id}'
YOUTUBE_CONSENT_URL = 'https://consent.youtube.com/save'
YOUTUBE_COMMUNITY_URL = 'https://www.youtube.com/@{community}/community'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'

SORT_BY_POPULAR = 0
SORT_BY_RECENT = 1

YT_CFG_RE = r'ytcfg\.set\s*\(\s*({.+?})\s*\)\s*;'
YT_INITIAL_DATA_RE = r'(?:window\s*\[\s*["\']ytInitialData["\']\s*\]|ytInitialData)\s*=\s*({.+?})\s*;\s*(?:var\s+meta|</script|\n)'
YT_HIDDEN_INPUT_RE = r'<input\s+type="hidden"\s+name="([A-Za-z0-9_]+)"\s+value="([A-Za-z0-9_\-\.]*)"\s*(?:required|)\s*>'


class YoutubeCommentDownloader:

    def __init__(self):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = USER_AGENT
        self.session.cookies.set('CONSENT', 'YES+cb', domain='.youtube.com')

    def ajax_request(self, endpoint, ytcfg, retries=5, sleep=20, timeout=60):
        url = 'https://www.youtube.com' + endpoint['commandMetadata']['webCommandMetadata']['apiUrl']

        data = {'context': ytcfg['INNERTUBE_CONTEXT'],
                'continuation': endpoint['continuationCommand']['token']}

        for _ in range(retries):
            try:
                response = self.session.post(url, params={'key': ytcfg['INNERTUBE_API_KEY']}, json=data, timeout=timeout)
                if response.status_code == 200:
                    return response.json()
                if response.status_code in [403, 413]:
                    return {}
            except requests.exceptions.Timeout:
                pass
            time.sleep(sleep)

    def get_comments(self, youtube_id, debug, *args, **kwargs):
        return self.get_comments_from_url(YOUTUBE_VIDEO_URL.format(youtube_id=youtube_id), debug, *args, **kwargs)

    def get_comments_from_url(self, youtube_url, debug=None, sort_by=SORT_BY_RECENT, language=None, sleep=.1):
        response = self.session.get(youtube_url)

        if 'consent' in str(response.url):
            # We may get redirected to a separate page for cookie consent. If this happens we agree automatically.
            params = dict(re.findall(YT_HIDDEN_INPUT_RE, response.text))
            params.update({'continue': youtube_url, 'set_eom': False, 'set_ytc': True, 'set_apyt': True})
            response = self.session.post(YOUTUBE_CONSENT_URL, params=params)

        html = response.text
        if debug:
            with open(f"{debug}/ytResponse.html", 'w', encoding='utf-8') as f:
                f.write(html)
        ytcfg = json.loads(self.regex_search(html, YT_CFG_RE, default=''))
        if not ytcfg:
            return  # Unable to extract configuration
        elif debug:
            with open(f"{debug}/ytcfg.json", 'w', encoding='utf-8') as f:
                json.dump(ytcfg, f, ensure_ascii=False, indent=4)
        if language:
            ytcfg['INNERTUBE_CONTEXT']['client']['hl'] = language

        data = json.loads(self.regex_search(html, YT_INITIAL_DATA_RE, default=''))
        if debug:
            with open(f"{debug}/ytInitialData.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

        item_section = next(self.search_dict(data, 'itemSectionRenderer'), None)
        renderer = next(self.search_dict(item_section, 'continuationItemRenderer'), None) if item_section else None
        if not renderer:
            # Comments disabled?
            return

        sort_menu = next(self.search_dict(data, 'sortFilterSubMenuRenderer'), {}).get('subMenuItems', [])
        if not sort_menu:
            # No sort menu. Maybe this is a request for community posts?
            section_list = next(self.search_dict(data, 'sectionListRenderer'), {})
            continuations = list(self.search_dict(section_list, 'continuationEndpoint'))
            # Retry..
            data = self.ajax_request(continuations[0], ytcfg) if continuations else {}
            sort_menu = next(self.search_dict(data, 'sortFilterSubMenuRenderer'), {}).get('subMenuItems', [])
        if not sort_menu or sort_by >= len(sort_menu):
            raise RuntimeError('Failed to set sorting')
        continuations = [sort_menu[sort_by]['serviceEndpoint']]

        continuation_count = 0
        while continuations:
            continuation = continuations.pop()
            response = self.ajax_request(continuation, ytcfg)

            if not response:
                break

            error = next(self.search_dict(response, 'externalErrorMessage'), None)
            if error:
                raise RuntimeError('Error returned from server: ' + error)

            actions = list(self.search_dict(response, 'reloadContinuationItemsCommand')) + \
                      list(self.search_dict(response, 'appendContinuationItemsAction'))
            for action in actions:
                for item in action.get('continuationItems', []):
                    if debug:
                        with open(f"{debug}/{continuation_count}_action_{actions.index(action)}_Item_{action.get('continuationItems', []).index(item)}.json", 'w', encoding='utf-8') as f:
                            json.dump(actions, f, ensure_ascii=False, indent=4)
                    if action['targetId'] in ['comments-section',
                                              'engagement-panel-comments-section',
                                              'shorts-engagement-panel-comments-section']:
                        # Process continuations for comments and replies.
                        continuations[:0] = [ep for ep in self.search_dict(item, 'continuationEndpoint')]
                    if action['targetId'].startswith('comment-replies-item') and 'continuationItemRenderer' in item:
                        # Process the 'Show more replies' button
                        continuations.append(next(self.search_dict(item, 'buttonRenderer'))['command'])

            surface_payloads = self.search_dict(response, 'commentSurfaceEntityPayload')
            payments = {payload['key']: next(self.search_dict(payload, 'simpleText'), '')
                        for payload in surface_payloads if 'pdgCommentChip' in payload}
            if payments:
                # We need to map the payload keys to the comment IDs.
                view_models = [vm['commentViewModel'] for vm in self.search_dict(response, 'commentViewModel')]
                surface_keys = {vm['commentSurfaceKey']: vm['commentId']
                                for vm in view_models if 'commentSurfaceKey' in vm}
                payments = {surface_keys[key]: payment for key, payment in payments.items() if key in surface_keys}

            toolbar_payloads = self.search_dict(response, 'engagementToolbarStateEntityPayload')
            toolbar_states = {payload['key']: payload for payload in toolbar_payloads}
            for comment in reversed(list(self.search_dict(response, 'commentEntityPayload'))):
                properties = comment['properties']
                cid = properties['commentId']
                author = comment['author']
                toolbar = comment['toolbar']
                toolbar_state = toolbar_states[properties['toolbarStateKey']]
                result = {'cid': cid,
                          'text': properties['content']['content'],
                          'time': properties['publishedTime'],
                          'author': author['displayName'],
                          'channel': author['channelId'],
                          'votes': toolbar['likeCountNotliked'].strip() or "0",
                          'replies': toolbar['replyCount'],
                          'photo': author['avatarThumbnailUrl'],
                          'heart': toolbar_state.get('heartState', '') == 'TOOLBAR_HEART_STATE_HEARTED',
                          'reply': '.' in cid}

                try:
                    result['time_parsed'] = dateparser.parse(result['time'].split('(')[0].strip()).timestamp()
                except AttributeError:
                    pass

                if cid in payments:
                    result['paid'] = payments[cid]

                continuation_count += 1
                yield result
            time.sleep(sleep)

    def get_community(self, community, debug, *args, **kwargs):
        print(community)
        return self.get_community_from_url(YOUTUBE_COMMUNITY_URL.format(community=f'{community[1:] if community.startswith('@') else community}'), debug, *args, **kwargs)

    def get_community_from_url(self, community_url, debug=None, sort_by=SORT_BY_RECENT, language=None, sleep=.1):
        response = self.session.get(community_url)
        if 'consent' in str(response.url):
            # We may get redirected to a separate page for cookie consent. If this happens we agree automatically.
            params = dict(re.findall(YT_HIDDEN_INPUT_RE, response.text))
            params.update({'continue': community_url, 'set_eom': False, 'set_ytc': True, 'set_apyt': True})
            response = self.session.post(YOUTUBE_CONSENT_URL, params=params)

        html = response.text
        if debug:
            with open(f"{debug}/ytResponse.html", 'w', encoding='utf-8') as f:
                f.write(html)

        ytcfg = json.loads(self.regex_search(html, YT_CFG_RE, default=''))
        if not ytcfg:
            return  # Unable to extract configuration
        elif debug:
            with open(f"{debug}/ytcfg.json", 'w', encoding='utf-8') as f:
                json.dump(ytcfg, f, ensure_ascii=False, indent=4)

        if language:
            ytcfg['INNERTUBE_CONTEXT']['client']['hl'] = language

        data = json.loads(self.regex_search(html, YT_INITIAL_DATA_RE, default=''))
        if debug:
            with open(f"{debug}/ytInitialData.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

        item_section = self.search_dict(data, 'itemSectionRenderer')
        for item in item_section:
            if "sectionIdentifier" in item:
                if item['sectionIdentifier'] == "backstage-item-section":
                    item_section = item
        renderer = next(self.search_dict(item_section, 'continuationItemRenderer'), None) if item_section else None
        if not renderer:
            # Comments disabled?
            return

        continuations = [renderer['continuationEndpoint']]
        
        continuation_count = 0
        while continuations:
            continuation = continuations.pop()
            response = self.ajax_request(continuation, ytcfg)

            if not response:
                break

            error = next(self.search_dict(response, 'externalErrorMessage'), None)
            if error:
                raise RuntimeError('Error returned from server: ' + error)

            actions = list(self.search_dict(response, 'reloadContinuationItemsCommand')) + \
                      list(self.search_dict(response, 'appendContinuationItemsAction'))
            for action in actions:
                for item in action.get('continuationItems', []):
                    if debug:
                        with open(f"{debug}/{continuation_count}_action_{actions.index(action)}_Item_{action.get('continuationItems', []).index(item)}.json", 'w', encoding='utf-8') as f:
                            json.dump(actions, f, ensure_ascii=False, indent=4)
                    if action['targetId']:
                        # Process continuations for comments and replies.
                        continuations[:0] = [ep for ep in self.search_dict(item, 'continuationEndpoint')]

                    # TODO: map the payload keys to posts?
                    continuation_count += 1
                    yield item
            time.sleep(sleep)
    @staticmethod
    def regex_search(text, pattern, group=1, default=None):
        match = re.search(pattern, text)
        return match.group(group) if match else default

    @staticmethod
    def search_dict(partial, search_key):
        stack = [partial]
        while stack:
            current_item = stack.pop()
            if isinstance(current_item, dict):
                for key, value in current_item.items():
                    if key == search_key:
                        yield value
                    else:
                        stack.append(value)
            elif isinstance(current_item, list):
                stack.extend(current_item)
