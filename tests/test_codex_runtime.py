import unittest
from interlock.codex_runtime import summarize


def entry(trust='untrusted', enabled=True):
    return [{'hooks': [{'eventName':'preToolUse', 'command':'python3 /repo/bin/interlock-codex',
                        'enabled':enabled, 'trustStatus':trust}], 'errors':[]}]


class RuntimeStatusTests(unittest.TestCase):
    def test_untrusted_and_modified_are_inactive(self):
        for trust in ('untrusted','modified'):
            self.assertEqual(summarize(entry(trust))[0], 1)

    def test_trusted_but_disabled_is_inactive(self):
        self.assertEqual(summarize(entry('trusted',False))[0], 1)

    def test_trusted_and_managed_are_ready_not_runtime_verified(self):
        for trust in ('trusted','managed'):
            code, message, _ = summarize(entry(trust))
            self.assertEqual(code,0)
            self.assertIn('live smoke test',message)

    def test_no_hook_is_inactive(self):
        self.assertEqual(summarize([{'hooks':[]}])[0],1)

    def test_load_errors_are_unknown(self):
        data=entry('trusted');data[0]['errors']=[{'message':'failed'}]
        self.assertEqual(summarize(data)[0],2)

    def test_other_hook_does_not_count(self):
        data=entry('trusted');data[0]['hooks'][0]['eventName']='postToolUse'
        self.assertEqual(summarize(data)[0],1)
