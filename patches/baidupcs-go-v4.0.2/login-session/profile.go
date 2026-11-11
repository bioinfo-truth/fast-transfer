// WAP request profile adapted from Baidu-Login v1.4.1, MIT (iikira).
// Modified: fixed empty challenge fields, no retries or response URLs.
package main

import (
	"net/url"
	"strconv"
	"time"
)

func loginForm(username, encrypted, clock string) url.Values {
	timestampStr := strconv.FormatInt(time.Now().Unix(), 10) + "773_357"
	return url.Values{
		"username":     {username},
		"password":     {encrypted},
		"verifycode":   {""},
		"vcodestr":     {""},
		"isphone":      {"0"},
		"loginmerge":   {"1"}, // 加入这个, 不用判断是否手机号了
		"action":       {"login"},
		"uid":          {timestampStr},
		"skin":         {"default_v2"},
		"connect":      {"0"},
		"dv":           {"tk0.408376350146535171516806245342@oov0QqrkqfOuwaCIxUELn3oYlSOI8f51tbnGy-nk3crkqfOuwaCIxUou2iobENoYBf51tb4Gy-nk3cuv0ounk5vrkBynGyvn1QzruvN6z3drLJi6LsdFIe3rkt~4Lyz5ktfn1Qlrk5v5D5fOuwaCIxUobJWOI3~rkt~4Lyi5kBfni0vrk8~n15fOuwaCIxUobJWOI3~rkt~4Lyz5DQfn1oxrk0v5k5eruvN6z3drLneFYeVEmy-nk3c-qq6Cqw3h7CChwvi5-y-rkFizvmEufyr1By4k5bn15e5k0~n18inD0b5D8vn1Tyn1t~nD5~5T__ivmCpA~op5gr-wbFLhyFLnirYsSCIAerYnNOGcfEIlQ6I6VOYJQIvh515f51tf5DBv5-yln15f5DFy5myl5kqf5DFy5myvnktxrkT-5T__Hv0nq5myv5myv4my-nWy-4my~n-yz5myz4Gyx4myv5k0f5Dqirk0ynWyv5iTf5DB~rk0z5Gyv4kTf5DQxrkty5Gy-5iQf51B-rkt~4B__"},
		"getpassUrl":   {"/passport/getpass?clientfrom=&adapter=0&ssid=&from=&authsite=&bd_page_type=&uid=" + timestampStr + "&pu=&tpl=wimn&u=https://m.baidu.com/usrprofile%3Fuid%3D" + timestampStr + "%23logined&type=&bdcm=060d5ffd462309f7e5529822720e0cf3d7cad665&tn=&regist_mode=&login_share_strategy=&subpro=wimn&skin=default_v2&client=&connect=0&smsLoginLink=1&loginLink=&bindToSmsLogin=&overseas=&is_voice_sms=&subpro=wimn&hideSLogin=&forcesetpwd=&regdomestic="},
		"mobilenum":    {"undefined"},
		"servertime":   {clock},
		"gid":          {"DA7C3AE-AF1F-48C0-AF9C-F1882CA37CD5"},
		"logLoginType": {"wap_loginTouch"},
		"FP_UID":       {"0b58c206c9faa8349576163341ef1321"},
		"traceid":      {""},
	}
}
