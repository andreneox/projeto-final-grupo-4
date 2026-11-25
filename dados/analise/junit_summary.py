import xml.etree.ElementTree as ET, collections, sys, json
D = r"C:\Users\johng\AppData\Local\Temp\claude\5d4b98baeb9c066d\2cfb3df3-19ce-4d01-a786-e84e1fafb8c3\scratchpad"
out = {}
for name in ["mock", "gateway"]:
    root = ET.parse(f"{D}\\junit_{name}.xml").getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    print("=====", name, {k: suite.get(k) for k in ["tests", "failures", "errors", "skipped", "time", "timestamp"]})
    per = collections.OrderedDict()
    for tc in suite.iter("testcase"):
        f = tc.get("classname").split(".")[-1]
        st = "passed"
        for child in tc:
            if child.tag in ("skipped", "failure", "error"):
                st = child.tag
                print("   ", child.tag, tc.get("name"), (child.get("message") or "")[:200])
        d = per.setdefault(f, {"passed": 0, "skipped": 0, "failure": 0, "error": 0, "time": 0.0, "names": []})
        d[st] += 1; d["time"] += float(tc.get("time")); d["names"].append(tc.get("name"))
    for f, d in per.items():
        print(f"  {f}: {d['passed']} ok, {d['skipped']} skip, {d['failure']+d['error']} falha, {d['time']:.2f}s")
        print("      ", "; ".join(d["names"]))
    out[name] = {"suite": {k: suite.get(k) for k in ["tests", "failures", "errors", "skipped", "time", "timestamp"]}, "files": per}
json.dump(out, open(f"{D}\\tests_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
