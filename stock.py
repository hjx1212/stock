import os
import re
import json
import requests

import hoshino
from hoshino import Service

sv = Service('股票')

type_map = {
    "11": "A股",
    "12": "B股",
    "13": "权证",
    "14": "期货",
    "15": "债券",
    "21": "开基",
    "22": "ETF",
    "23": "LOF",
    "24": "货基",
    "25": "QDII",
    "26": "封基",
    "31": "港股",
    "32": "窝轮",
    "33": "港指数",
    "41": "美股",
    "42": "外期",
    "71": "外汇",
    "72": "基金",  # 场内基金（带市场）
    "73": "新三板",
    "74": "板块",
    "75": "板块",  # 新浪行业
    "76": "板块",  # 申万行业
    "77": "板块",  # 申万二级
    "78": "板块",  # 热门概念（财汇概念）
    "79": "板块",  # 地域板块
    "80": "板块",  # 证监会行业
    "81": "债券",
    "82": "债券",
    "85": "期货",  # 内盘期货
    "86": "期货",  # 外盘期货
    "87": "期货",  # 内盘期货连续，股指期货连续，50ETF期权
    "88": "期货",  # 内盘股指期货
    "100": "指数",  # 全球指数
    "101": "基金",  # 所有基金
    "102": "指数",  # 全部板块指数(概念、地域、行业)
    "103": "英股",
    "104": "国债",  # （目前暂时是美国国债）
    "105": "ETF",  # 美股ETF,国际线索组-中文站）
    "106": "ETF",  # 美股ETF,国际线索组-英文站）
    "107": "msci",
    "111": "A股",
    "120": "债券"
}
supported_type_list = ["11", "12", "13", "14", "15", '31', '32', '33', '41', '42', '71', '73']
content_re = re.compile(r'var (.*)="(.*)";')
subscription = {}


def http_query(url):
    content = requests.get(url).content.decode('gb18030')
    return content_re.findall(content)


def get_stock_info(stock_list):
    resp = http_query(f'https://hq.sinajs.cn/list={",".join(stock_list)}')
    infos = []
    for k, v in resp:
        name = ""
        if v:
            sps = v.split(',')
            if k.startswith('hq_str_s_'):
                name, cur, delta, p_delta, _, _ = sps
            elif k.startswith('hq_str_rt_'):
                name, cur, delta, p_delta = sps[1], sps[6], sps[7], sps[8]
            elif k.startswith('hq_str_gb_'):
                name, cur, delta, p_delta = sps[0], sps[1], sps[4], sps[2]
            elif len(sps) == 11:
                name, cur, base = sps[9], sps[1], sps[3]
                cur = float(cur)
                base = float(base)
                delta = cur - base
                p_delta = delta / base * 100
        if name != "":
            infos.append({
                'name': name,
                'cur': float(cur),
                'delta': float(delta),
                'p_delta': float(p_delta),
            })
        else:
            infos.append({'error': f'{k[7:]}: {"暂不支持该格式，请联系维护人员处理" if v else "查询结果为空"}'})
    return infos


def get_suggest(key, s_type=None):
    if s_type is None:
        s_type = ['11', '12', '13', '14', '15']
    key = key.lower()
    resp = http_query(
        f'https://suggest3.sinajs.cn/suggest/type={",".join(map(str, s_type))}&key={key}&name=suggest')
    if len(resp) <= 0 or not resp[0][1]:
        return []
    resp = resp[0][1].split(';')
    suggests = []
    for v in resp:
        sps = v.split(',')
        info = {
            # 'key': sps[0],
            'type': sps[1],
            # 'code_short': sps[2],
            'code': sps[3],
            'name': sps[4],
        }
        if sps[0].lower() == key or sps[3].lower() == key or sps[4].lower() == key:
            return [info]
        suggests.append(info)
    return suggests


def fmt_stock_key(key):
    if isinstance(key, str):
        return 's_' + key
    if isinstance(key, dict):
        if key['type'] in ('11', '12', '13', '14', '15'):  # 沪深
            return 's_' + key['code']
        elif key['type'] in ('21', '22', '23', '24', '25', '26'):  # 基金
            return key['code']
        elif key['type'] in ('31', '32', '33'):  # 港股
            return 'rt_hk' + key['code'].upper()
        elif key['type'] in ('41', '42'):  # 美股
            return 'gb_' + key['code'].lstrip('.')
        elif key['type'] == '71':  # 外汇
            return key['code'].upper()
        elif key['type'] == '73':  # 新三板
            return 's_' + key['code']
        elif key['type'] == '85':  # 期货
            pass
        return key['code']
    if isinstance(key, list) or isinstance(key, tuple):
        return map(fmt_stock_key, key)
    raise TypeError(f'unsupported type {type(key)}')


def fmt_stock_info(infos):
    return '\n'.join(
        f'{x["name"]}\t{x["cur"]:.2f}\t{"📈" if x["p_delta"] >= 0 else "📉"}{x["p_delta"]:+.2f}% ({x["delta"]:+.2f})'
        if x.get('name') else x.get('error') for x in infos)


def save_stock_subscription():
    config_file = os.path.join(os.path.dirname(__file__), 'subscription.json')
    try:
        with open(config_file, 'w', encoding='utf8') as f:
            json.dump(subscription, f, ensure_ascii=False, indent=2)
    except Exception as e:
        sv.logger.error(f'Error: {e}')


def load_stock_subscription():
    config_file = os.path.join(os.path.dirname(__file__), 'subscription.json')
    try:
        with open(config_file, 'r', encoding='utf8') as f:
            global subscription
            subscription = json.load(f)
    except Exception as e:
        sv.logger.error(f'Error: {e}')


def get_stock_subscription_group(gid, auto_create=False):
    if subscription.get('group') is None:
        subscription['group'] = {}
    if subscription['group'].get(gid) is None:
        if not auto_create:
            return None
        subscription['group'][gid] = {'list': [], 'notify': True}
    return subscription['group'][gid]


@sv.on_prefix(["股票查询"])
async def stock_query(bot, ev):
    key = ev.message.extract_plain_text()
    if not key:
        # await bot.send(ev, '请填写股票关键词')
        await stock_subscription_query(bot, ev)
        return
    suggests = get_suggest(key, supported_type_list)
    if not suggests:
        await bot.send(ev, f'{key}: 查询结果为空')
        return
    msg = fmt_stock_info(get_stock_info(fmt_stock_key(suggests)))
    if len(suggests) == 1:
        if suggests[0]['type'] in ('11', '12', '13', '14', '15'):  # 沪深
            msg += f'\n[CQ:image,file=http://image.sinajs.cn/newchart/min/n/{suggests[0]["code"]}.gif,cache=0]' \
                   f'\n[CQ:image,file=http://image.sinajs.cn/newchart/daily/n/{suggests[0]["code"]}.gif,cache=0]'
        elif suggests[0]['type'] in ('31', '32', '33'):  # 港股
            msg += f'\n[CQ:image,file=http://image.sinajs.cn/newchart/hk_stock/min/{suggests[0]["code"]}.gif,cache=0]' \
                   f'\n[CQ:image,file=http://image.sinajs.cn/newchart/hk_stock/daily/{suggests[0]["code"]}.gif,cache=0]'
        elif suggests[0]['type'] in ('41', '42'):  # 美股
            msg += f'\n[CQ:image,file=http://image.sinajs.cn/newchart/usstock/min/{suggests[0]["code"]}.gif,cache=0]' \
                   f'\n[CQ:image,file=http://image.sinajs.cn/newchart/usstock/daily/{suggests[0]["code"]}.gif,cache=0]'
        elif suggests[0]['type'] == '71':  # 外汇
            msg += f'\n[CQ:image,file=http://image.sinajs.cn/newchart/v5/forex/min/{suggests[0]["code"]}.gif,cache=0]' \
                   f'\n[CQ:image,file=http://image.sinajs.cn/newchart/v5/forex/k/day/{suggests[0]["code"]}.gif,cache=0]'
    await bot.send(ev, f'{key}: 查询到以下结果:\n{msg}')


@sv.on_prefix(["股票添加", "股票订阅", "股票添加订阅", "股票订阅添加"])
async def stock_add(bot, ev):
    key = ev.message.extract_plain_text()
    if not key:
        await bot.send(ev, '请填写股票关键词')
        return
    suggests = get_suggest(key, supported_type_list)
    if not suggests:
        suggests = get_suggest(key, [])
    if not suggests:
        await bot.send(ev, f'{key}: 查询结果为空')
        return
    if len(suggests) > 1:
        msg = f'{key}: 查询到以下结果, 请输入准确的名称或代码来订阅:\n类型\t代码\t名称'
        for sg in suggests:
            msg += f'\n{type_map[sg["type"]]}\t{sg["code"]}\t{sg["name"]}'
        await bot.send(ev, msg)
        return
    sg = suggests[0]
    sub = get_stock_subscription_group(str(ev.group_id), auto_create=True)
    if not sub.get('list'):
        sub['list'] = [sg]
    elif [x for x in sub['list'] if x['type'] == sg['type'] and x['code'] == sg['code']]:
        await bot.send(ev, f'{sg["name"]} 已存在，请勿重复添加!')
        return
    else:
        sub['list'].append(sg)
    save_stock_subscription()
    await bot.send(ev, f'{sg["name"]} 订阅成功~')


@sv.on_prefix(["股票删除", "股票取消订阅", "股票删除订阅", "股票订阅取消", "股票订阅删除"])
async def stock_delete(bot, ev):
    key = ev.message.extract_plain_text()
    if not key:
        await bot.send(ev, '请填写股票关键词')
        return
    suggests = get_suggest(key, supported_type_list)
    if not suggests:
        suggests = get_suggest(key, [])
    if not suggests:
        await bot.send(ev, f'{key}: 查询结果为空')
        return
    if len(suggests) > 1:
        # TODO 先和订阅列表做匹配，若只有一个则删除，若多个则只提示这几个而不是全部搜索列表
        msg = f'{key}: 查询到以下结果, 请输入准确的名称或代码来取消订阅:\n类型\t代码\t名称'
        for sg in suggests:
            msg += f'\n{type_map[sg["type"]]}\t{sg["code"]}\t{sg["name"]}'
        await bot.send(ev, msg)
        return
    sg = suggests[0]
    sub = get_stock_subscription_group(str(ev.group_id))
    if not sub or not sub.get('list'):
        await bot.send(ev, '没有订阅列表!')
        return
    new_list = [x for x in sub['list'] if x['type'] != sg['type'] or x['code'] != sg['code']]
    if len(new_list) == len(sub['list']):
        await bot.send(ev, f'{sg["name"]} 没有被订阅!')
        return
    sub['list'] = new_list
    save_stock_subscription()
    await bot.send(ev, f'{sg["name"]} 取消订阅成功~')


@sv.on_prefix(["股票清空", "股票清空订阅", "股票订阅清空"])
async def stock_clear(bot, ev):
    sub = get_stock_subscription_group(str(ev.group_id))
    if not sub or not sub.get('list'):
        await bot.send(ev, '没有订阅列表!')
        return
    sub['list'] = []
    save_stock_subscription()
    await bot.send(ev, '清空订阅成功~')


@sv.on_prefix(["股票查询订阅", "股票订阅查询"])
async def stock_subscription_query(bot, ev):
    sub = get_stock_subscription_group(str(ev.group_id))
    if not sub or not sub.get('list'):
        await bot.send(ev, '没有订阅列表!')
        return
    await bot.send(ev, fmt_stock_info(get_stock_info(fmt_stock_key(sub['list']))))


@sv.on_prefix(["股票打开推送", "股票推送打开", "股票推送on"])
async def stock_notify_on(bot, ev):
    sub = get_stock_subscription_group(str(ev.group_id))
    if not sub:
        await bot.send(ev, '没有订阅列表!')
        return
    if sub.get('notify'):
        await bot.send(ev, '推送已是打开状态')
        return
    sub['notify'] = True
    save_stock_subscription()
    await bot.send(ev, '打开推送成功~')


@sv.on_prefix(["股票关闭推送", "股票推送关闭", "股票推送off"])
async def stock_notify_off(bot, ev):
    sub = get_stock_subscription_group(str(ev.group_id))
    if not sub:
        await bot.send(ev, '没有订阅列表!')
        return
    if not sub.get('notify'):
        await bot.send(ev, '推送已是关闭状态')
        return
    sub['notify'] = False
    save_stock_subscription()
    await bot.send(ev, '关闭推送成功~')


async def stock_subscription_notify():
    if not subscription['group']:
        return
    bot = hoshino.get_bot()
    for gid in await sv.get_enable_groups():
        sub = get_stock_subscription_group(str(gid))
        if not sub or not sub.get('notify') or not sub.get('list'):
            continue
        try:
            await bot.send_group_msg(group_id=gid, message=fmt_stock_info(get_stock_info(fmt_stock_key(sub['list']))))
        except:
            pass


# TODO 定时提醒暂时就保持写死的这几个，之后考虑变成方便配置或调整
@sv.scheduled_job('cron', minute=35, hour=9, day_of_week='1-5')
async def _1():
    await stock_subscription_notify()


@sv.scheduled_job('cron', minute=31, hour=11, day_of_week='1-5')
async def _2():
    await stock_subscription_notify()


@sv.scheduled_job('cron', minute=1, hour=15, day_of_week='1-5')
async def _3():
    await stock_subscription_notify()


# TODO 没有订阅美股可以考虑不推送
# TODO 美国时间夏令冬令支持
@sv.scheduled_job('cron', minute=0, hour=23, day_of_week='1-5')
async def _4():
    await stock_subscription_notify()


@sv.scheduled_job('cron', minute=1, hour=5, day_of_week='2-6')
async def _5():
    await stock_subscription_notify()


load_stock_subscription()

if __name__ == '__main__':
    # print(get_stock_info(['s_sh000001', 's_sz399001', 'gb_ixic', 'USDCNY']))
    # print(get_suggest('hryy', []))
    print(fmt_stock_info(get_stock_info(fmt_stock_key(get_suggest('00001', [])))))
