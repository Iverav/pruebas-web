(() => {
  const el = id => document.getElementById(id);
  let urls = [];
  const clearURLs = () => { for (const url of urls) URL.revokeObjectURL(url); urls = []; };
  const uniqueName = (original, used) => {
    let name = original.replace(/[\\/\x00-\x1f]/g, '_') || 'foto.jpg';
    const dot = name.lastIndexOf('.');
    const base = dot > 0 ? name.slice(0, dot) : name;
    const ext = dot > 0 ? name.slice(dot) : '';
    let number = 2;
    while (used.has(name.toLocaleLowerCase())) name = `${base} (${number++})${ext}`;
    used.add(name.toLocaleLowerCase());
    return name;
  };
  const crcTable = (() => {
    let table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; table[n] = c >>> 0; }
    return table;
  })();
  const crc32 = bytes => { let crc = 0xffffffff; for (const b of bytes) crc = crcTable[(crc ^ b) & 255] ^ (crc >>> 8); return (crc ^ 0xffffffff) >>> 0; };
  // ZIP sin compresión adicional: los JPEG ya están comprimidos.
  async function makeZip(files) {
    const local = [], central = []; let offset = 0;
    const encoder = new TextEncoder();
    for (const file of files) {
      const name = encoder.encode(file.name), data = new Uint8Array(await file.blob.arrayBuffer()), crc = crc32(data);
      const h = new Uint8Array(30 + name.length), v = new DataView(h.buffer);
      v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,0x800,true);v.setUint32(14,crc,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,name.length,true);h.set(name,30);
      const c = new Uint8Array(46 + name.length), cv = new DataView(c.buffer);
      cv.setUint32(0,0x02014b50,true);cv.setUint16(4,20,true);cv.setUint16(6,20,true);cv.setUint16(8,0x800,true);cv.setUint32(16,crc,true);cv.setUint32(20,data.length,true);cv.setUint32(24,data.length,true);cv.setUint16(28,name.length,true);cv.setUint32(42,offset,true);c.set(name,46);
      local.push(h,data);central.push(c);offset += h.length + data.length;
    }
    const centralSize = central.reduce((n,c) => n+c.length,0), footer = new Uint8Array(22), v = new DataView(footer.buffer);
    v.setUint32(0,0x06054b50,true);v.setUint16(8,files.length,true);v.setUint16(10,files.length,true);v.setUint32(12,centralSize,true);v.setUint32(16,offset,true);
    return new Blob([...local,...central,footer],{type:'application/zip'});
  }
  function link(blob, name, label, parent) {
    const url = URL.createObjectURL(blob); urls.push(url);
    const a = document.createElement('a'); a.href=url; a.download=name; a.textContent=label; a.className='download'; a.style.margin='8px 8px 0 0'; parent.appendChild(a);
  }
  el('mobileFiles').addEventListener('change', () => {
    clearURLs(); el('mobileResults').replaceChildren(); el('mobileLog').hidden=true;
    let n=el('mobileFiles').files.length; el('mobileCount').textContent=n ? `${n} foto${n===1?'':'s'} seleccionada${n===1?'':'s'}.` : 'Aún no has seleccionado fotos.';
    el('mobileStatus').textContent='Selecciona el tamaño y pulsa Reducir fotos.';
  });
  el('mobileRun').addEventListener('click', async () => {
    const files=Array.from(el('mobileFiles').files);
    if (!files.length) { el('mobileStatus').textContent='Selecciona al menos una foto JPG.'; return; }
    if (files.length > 500) { el('mobileStatus').textContent='Selecciona como máximo 500 fotos por lote.'; return; }
    clearURLs(); el('mobileResults').replaceChildren(); el('mobileLog').textContent=''; el('mobileLog').hidden=true;
    el('mobileRun').disabled=true; el('mobileFiles').disabled=true; el('mobileProgress').max=files.length; el('mobileProgress').value=0;
    const output=[], used=new Set(), dims=el('mobileSize').value.split(',').map(Number), mode=document.querySelector('[name=mobileFormat]:checked').value;
    try {
      for (let i=0; i<files.length; i++) {
        const f=files[i];
        try {
          if (!/\.(jpe?g|jfif)$/i.test(f.name) && f.type!=='image/jpeg') throw Error('Solo se admiten fotos JPEG en esta versión.');
          const result=await encodePhoto(f,dims,mode);
          result.name=uniqueName(result.name,used); output.push(result);
        } catch(e) { el('mobileLog').hidden=false; el('mobileLog').textContent+=`${f.name}: ${e.message}\n`; }
        el('mobileProgress').value=i+1;el('mobileStatus').textContent=`Procesando ${i+1} de ${files.length}…`;
        await new Promise(resolve=>setTimeout(resolve,0));
      }
      if(output.length===1) link(output[0].blob,output[0].name,'Descargar foto',el('mobileResults'));
      if(output.length>1) {
        el('mobileStatus').textContent='Preparando archivo con las fotos…';
        const total=output.reduce((sum,item)=>sum+item.blob.size,0);
        if(total<=150*1024*1024) link(await makeZip(output),'Fotos-reducidas.zip',`Descargar ${output.length} fotos (ZIP)`,el('mobileResults'));
        else {const note=document.createElement('p');note.textContent='El lote es grande. Descarga las fotos individualmente o procesa lotes más pequeños.';el('mobileResults').appendChild(note);}
        const details=document.createElement('details'), summary=document.createElement('summary'); summary.textContent='Descargar fotos individualmente';details.appendChild(summary);output.forEach(item=>link(item.blob,item.name,item.name,details));el('mobileResults').appendChild(details);
      }
      el('mobileStatus').textContent=`Listo: ${output.length} de ${files.length} fotos procesadas. Tus originales no se modificaron.`;
    } catch(e) { el('mobileStatus').textContent='No se pudo completar el proceso: '+e.message; }
    finally {el('mobileRun').disabled=false;el('mobileFiles').disabled=false;}
  });
})();

