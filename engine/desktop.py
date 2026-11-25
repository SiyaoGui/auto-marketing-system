"""Small local desktop launcher. No browser server, hosted dashboard or subscription."""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from .core import ROOT


def main():
    app = tk.Tk()
    app.title('本地营销工作流')
    app.geometry('1000x720')
    app.configure(bg='#101a24')
    events = queue.Queue()
    active = {'process': None}
    tk.Label(app,text='本地营销工作流',font=('Microsoft YaHei',24,'bold'),bg='#101a24',fg='#b8f5d1').pack(anchor='w',padx=28,pady=(22,5))
    tk.Label(app,text='先配置公司与素材，再连接账号。演示视频不会发布。',font=('Microsoft YaHei',11),bg='#101a24',fg='#d4e0dc').pack(anchor='w',padx=28,pady=(0,18))
    bar = ttk.Frame(app)
    bar.pack(fill='x',padx=28)
    out = tk.Text(app,bg='#182b34',fg='#e2ece7',insertbackground='white',font=('Consolas',11),wrap='word')
    out.pack(fill='both',expand=True,padx=28,pady=20)

    def worker(args):
        env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONUNBUFFERED': '1'}
        try:
            process = subprocess.Popen([sys.executable,'-m','engine.cli',*args],cwd=ROOT,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            active['process'] = process
            for line in process.stdout:
                events.put(line)
            process.wait()
            events.put(f'\n完成，退出码 {process.returncode}\n')
        except Exception as exc:
            events.put(f'无法执行：{type(exc).__name__}\n')
        finally:
            active['process'] = None

    def launch(*args):
        if active['process'] is not None:
            messagebox.showinfo('正在运行','当前任务仍在运行。请等待，或停止本窗口启动的工作进程。')
            return
        out.insert('end','\n> ' + ' '.join(args) + '\n')
        # Reserve the slot before the thread starts.
        active['process'] = 'starting'
        threading.Thread(target=worker,args=(args,),daemon=True).start()

    def stop():
        proc = active['process']
        if proc and proc != 'starting':
            proc.terminate()
            events.put('停止信号已发送。若正在上传，稍后先核对平台结果。\n')

    for label, command in [('环境诊断','doctor'),('制作演示','demo'),('生成今日内容','run'),('查看队列','status'),('启动自动运行','daemon')]:
        ttk.Button(bar,text=label,command=lambda c=command:launch(c)).pack(side='left',padx=3,pady=5)
    ttk.Button(bar,text='停止',command=stop).pack(side='left',padx=3)
    nav = ttk.Frame(app)
    nav.pack(fill='x',padx=28,pady=(0,20))
    def open_path(path):
        if os.name == 'nt':
            os.startfile(str(path))
    ttk.Button(nav,text='打开公司配置',command=lambda:open_path(ROOT/'brands')).pack(side='left',padx=3)
    ttk.Button(nav,text='打开素材与关键词',command=lambda:open_path(ROOT/'data')).pack(side='left',padx=3)
    ttk.Button(nav,text='打开使用说明',command=lambda:open_path(ROOT/'README.zh-CN.md')).pack(side='left',padx=3)
    ttk.Button(nav,text='打开运行报告',command=lambda:open_path(ROOT/'output/report.html')).pack(side='left',padx=3)
    def poll():
        while not events.empty():
            out.insert('end',events.get())
            out.see('end')
        app.after(150,poll)
    def close():
        if active['process'] and not messagebox.askyesno('正在运行','关闭窗口将停止当前工作进程。仍要关闭吗？'):
            return
        stop()
        app.destroy()
    app.protocol('WM_DELETE_WINDOW',close)
    poll()
    launch('doctor')
    app.mainloop()


if __name__ == '__main__':
    main()
