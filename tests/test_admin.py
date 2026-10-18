"""Administrator SSH must not steal the caller's deployment script input."""
import subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from deploy_lab import Admin

class AdministratorTransportTests(unittest.TestCase):
    def setUp(self):self.admin=Admin({'nodes':{'owned':'10.1.1.82'},'known_hosts_directory':'pins','ssh_key':'private-key-path','user':'ubuntu'})
    def test_read_only_commands_cannot_consume_parent_script(self):
        replies=[subprocess.CompletedProcess([],0,stdout=b'owned\n'),subprocess.CompletedProcess([],0,stdout=b'ok')]
        with patch('deploy_lab.subprocess.run',side_effect=replies) as run:
            self.assertEqual(self.admin.run('owned','fixed check'),b'ok')
            self.assertTrue(all(call.kwargs.get('stdin')==subprocess.DEVNULL for call in run.call_args_list))
    def test_explicit_upload_bytes_still_reach_remote_stdin(self):
        self.admin.verified.add('owned')
        with patch('deploy_lab.subprocess.run',return_value=subprocess.CompletedProcess([],0,stdout=b'')) as run:
            self.admin.run('owned','fixed upload',b'public source')
            self.assertEqual(run.call_args.kwargs['input'],b'public source')
            self.assertNotIn('stdin',run.call_args.kwargs)

if __name__=='__main__':unittest.main()
