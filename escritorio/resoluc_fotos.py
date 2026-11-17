import os, sys, threading, queue, pathlib, traceback
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / 'vendor'))
from PIL import Image, ImageOps, PngImagePlugin
from pillow_heif import register_heif_opener
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

register_heif_opener()
EXTS={'.jpg','.jpeg','.jfif','.png','.bmp','.heic','.heif'}

def convert(src, dest, bounds, mode, quality=85):
    suffix = '.jpg' if mode == 'jpg' else src.suffix.lower()
    output = dest.with_suffix(suffix)
    if output.exists(): raise ValueError('Ya existe un archivo de salida con este nombre')
    output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        source_info = dict(im.info)
        exif = im.getexif()
        im = ImageOps.exif_transpose(im)
        im.thumbnail(bounds, Image.Resampling.LANCZOS)
        fmt = 'JPEG' if mode == 'jpg' or suffix in ('.jpg','.jpeg','.jfif') else {'.png':'PNG','.bmp':'BMP','.heic':'HEIF','.heif':'HEIF'}[suffix]
        if fmt == 'JPEG':
            if im.mode in ('RGBA','LA') or (im.mode == 'P' and 'transparency' in source_info):
                rgba=im.convert('RGBA'); base=Image.new('RGB',rgba.size,'white'); base.paste(rgba,mask=rgba.getchannel('A')); im=base
            elif im.mode != 'RGB': im=im.convert('RGB')
        kwargs={}
        exif_bytes=im.getexif().tobytes() if im.getexif() else b''
        if exif_bytes and fmt in ('JPEG','PNG','HEIF'): kwargs['exif']=exif_bytes
        if source_info.get('icc_profile') and fmt in ('JPEG','PNG','HEIF'): kwargs['icc_profile']=source_info['icc_profile']
        if fmt=='JPEG':
            kwargs.update(quality=quality, optimize=True)
            if source_info.get('xmp'): kwargs['xmp']=source_info['xmp']
        if fmt=='PNG':
            info=PngImagePlugin.PngInfo()
            for k,v in source_info.items():
                if isinstance(v,str) and k not in ('exif','icc_profile'): info.add_text(k,v)
            kwargs['pnginfo']=info
        # A BMP encoder cannot carry EXIF/ICC. Do not silently discard those fields.
        if fmt=='BMP' and (exif_bytes or source_info.get('icc_profile') or source_info.get('xmp')):
            raise ValueError('BMP no puede conservar estos metadatos; prueba salida JPG')
        temp=output.with_name(output.name+'.tmp')
        try:
            im.save(temp,format=fmt,**kwargs)
            with Image.open(temp) as check:
                check.verify()
            os.rename(temp,output)
        finally:
            if temp.exists(): temp.unlink()
    return output

class App:
 def __init__(self,root):
    self.root=root; root.title('Resoluc Fotos | Prueba de escritorio'); root.geometry('720x650'); root.minsize(640,600)
    root.configure(bg='#f3f6f4'); self.source=tk.StringVar(); self.dest=tk.StringVar(); self.mode=tk.StringVar(value='jpg'); self.res=tk.StringVar(value='1600 x 1200'); self.busy=False
    box=ttk.Frame(root,padding=24); box.pack(fill='both',expand=True)
    ttk.Label(box,text='Resoluc Fotos',font=('Segoe UI',22,'bold')).pack(anchor='w')
    ttk.Label(box,text='Reduce fotos en carpetas y subcarpetas, sin modificar los originales.',wraplength=650).pack(anchor='w',pady=(3,18))
    self.pathrow(box,'1. Carpeta de fotos',self.source)
    self.pathrow(box,'2. Carpeta de destino para las copias',self.dest)
    ttk.Label(box,text='3. Formato de salida',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(14,4))
    ttk.Radiobutton(box,text='Convertir a JPG para fichas técnicas',variable=self.mode,value='jpg').pack(anchor='w')
    ttk.Radiobutton(box,text='Conservar el formato original',variable=self.mode,value='original').pack(anchor='w')
    ttk.Label(box,text='4. Tamaño máximo (sin ampliar fotos pequeñas)',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(14,4))
    ttk.Combobox(box,textvariable=self.res,values=['480 x 240','800 x 600','1024 x 768','1600 x 1200'],state='readonly',width=20).pack(anchor='w')
    ttk.Label(box,text='Se intenta conservar EXIF, ubicación y perfil de color. Algunos metadatos pueden no ser compatibles; revisa el informe. HEIC depende de los códecs disponibles.',wraplength=650).pack(anchor='w',pady=12)
    self.button=ttk.Button(box,text='Crear copias reducidas',command=self.start); self.button.pack(anchor='w')
    self.progress=ttk.Progressbar(box,mode='determinate'); self.progress.pack(fill='x',pady=(14,5))
    self.status=ttk.Label(box,text='Selecciona las carpetas para comenzar.'); self.status.pack(anchor='w')
    self.log=tk.Text(box,height=9,wrap='word',font=('Consolas',9)); self.log.pack(fill='both',expand=True,pady=(10,0)); self.q=queue.Queue(); root.after(100,self.drain)
 def pathrow(self,p,label,var):
    ttk.Label(p,text=label,font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(8,4)); row=ttk.Frame(p); row.pack(fill='x'); ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True); ttk.Button(row,text='Elegir…',command=lambda:var.set(filedialog.askdirectory() or var.get())).pack(side='left',padx=(8,0))
 def start(self):
    try:
     a=pathlib.Path(self.source.get()).resolve(); b=pathlib.Path(self.dest.get()).resolve()
     if not self.source.get() or not a.is_dir() or not self.dest.get() or not b.is_dir(): raise ValueError('Selecciona una carpeta de origen y otra de destino existentes.')
     if a==b or a in b.parents or b in a.parents: raise ValueError('El destino debe estar fuera de la carpeta de origen y viceversa.')
     bounds=tuple(map(int,self.res.get().split(' x ')))
    except Exception as e: messagebox.showerror('Revisa las carpetas',str(e)); return
    self.button.config(state='disabled'); self.log.delete('1.0','end'); self.status.config(text='Buscando fotos…'); threading.Thread(target=self.worker,args=(a,b,bounds,self.mode.get()),daemon=True).start()
 def worker(self,a,b,bounds,mode):
    try:
     errors=[]; files=[]
     def onerror(e): errors.append(str(e))
     for root,dirs,names in os.walk(a,followlinks=False,onerror=onerror):
      dirs[:]=[d for d in dirs if not (pathlib.Path(root)/d).is_symlink()]
      files.extend(pathlib.Path(root)/n for n in names if pathlib.Path(n).suffix.lower() in EXTS and not (pathlib.Path(root)/n).is_symlink())
     self.q.put(('total',len(files))); ok=0
     for i,p in enumerate(files,1):
      try:
       out=convert(p,b/p.relative_to(a),bounds,mode); ok+=1; msg=f'✓ {p.relative_to(a)} → {out.relative_to(b)}'
      except Exception as e: msg=f'ERROR {p.relative_to(a)}: {e}'; errors.append(msg)
      self.q.put(('item',(i,msg)))
     self.q.put(('done',(ok,len(files),errors)))
    except Exception as e: self.q.put(('fatal',str(e)))
 def drain(self):
    try:
     while True:
      t,v=self.q.get_nowait()
      if t=='total': self.progress['maximum']=max(v,1); self.progress['value']=0
      elif t=='item': self.progress['value']=v[0]; self.status.config(text=f'Procesadas: {v[0]}'); self.log.insert('end',v[1]+'\n'); self.log.see('end')
      elif t=='done':
       ok,total,errors=v; self.button.config(state='normal'); self.status.config(text=f'Listo: {ok} de {total}. Errores: {len(errors)}.'); messagebox.showinfo('Proceso terminado',f'Copias creadas: {ok} de {total}\nProblemas: {len(errors)}\nLos originales no se modificaron.')
      elif t=='fatal': self.button.config(state='normal'); messagebox.showerror('No se pudo completar',v)
    except queue.Empty: pass
    self.root.after(100,self.drain)
if __name__=='__main__':
 root=tk.Tk(); App(root); root.mainloop()

