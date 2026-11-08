import json
import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from trading.shadow_archive_pull import choose_runs, run_download

def stamp(h):
    return datetime.fromtimestamp(h,timezone.utc).isoformat()

class ArchiveSelectionTests(unittest.TestCase):
    def setUp(self):
        self.now=1_800_000_000_000
        self.h=self.now/1000

    def test_earliest_in_fixed_bucket_selected_not_best_signal(self):
        # Chosen purely by timestamp and GitHub success, never trade label.
        a=[{"databaseId":10,"createdAt":stamp(self.h-100),"conclusion":"success"},
           {"databaseId":11,"createdAt":stamp(self.h-80),"conclusion":"success"}]
        result=choose_runs(a,self.now,bucket_ms=7200*1000)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0],10)

    def test_failed_job_excluded(self):
        r=[{"databaseId":1,"createdAt":stamp(self.h-100),"conclusion":"failure"}]
        self.assertEqual(choose_runs(r,self.now),[])

    def test_outdated_and_future_events_excluded(self):
        runs=[{"databaseId":1,"createdAt":stamp(self.h-16*86400),"conclusion":"success"},
              {"databaseId":2,"createdAt":stamp(self.h+60),"conclusion":"success"},
              {"databaseId":3,"createdAt":stamp(self.h-60),"conclusion":"success"}]
        self.assertEqual(choose_runs(runs,self.now),[3])

    def test_limit_bounded_after_chronological_sort(self):
        runs=[{"databaseId":i+1,
               "createdAt":stamp(self.h-(i+1)*10800),
               "conclusion":"success"} for i in range(18)]
        result=choose_runs(runs,self.now,max_downloads=4)
        self.assertEqual(len(result),4)
        self.assertEqual(result[0],4)
        self.assertEqual(result[-1],1)

    def test_download_counts_expired_without_claiming_success(self):
        class Result:
            def __init__(self,out):self.stdout=out
        calls=[]
        def mock(args,**kwargs):
            calls.append(args)
            if args[:3]==["gh","run","list"]:
                return Result(json.dumps([{"databaseId":42,
                 "createdAt":stamp(self.h-100),
                 "conclusion":"success"}]))
            raise subprocess.CalledProcessError(1,args)
        with TemporaryDirectory() as folder:
            result=run_download(folder,executor=mock,now_ms=self.now)
        self.assertEqual(result["selected"],1)
        self.assertEqual(result["downloaded"],0)
        self.assertEqual(result["unavailable"],1)
        self.assertEqual(len(calls),2)

    def test_success_requires_actual_evidence_file(self):
        class Result:
            def __init__(self,out):self.stdout=out
        def mock(args,**kwargs):
            if args[:3]==["gh","run","list"]:
                return Result(json.dumps([{"databaseId":42,
                    "createdAt":stamp(self.h-100),
                    "conclusion":"success"}]))
            if args[:3]==["gh","run","download"]:
                Path(args[-1],"quant2037_snapshot.json").write_text("{}")
                return Result("")
            raise AssertionError(args)
        with TemporaryDirectory() as folder:
            result=run_download(folder,executor=mock,now_ms=self.now)
        self.assertEqual(result["selected"],1)
        self.assertEqual(result["downloaded"],1)
        self.assertEqual(result["unavailable"],0)

if __name__=="__main__":
    unittest.main()
