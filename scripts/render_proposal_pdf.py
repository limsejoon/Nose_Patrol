"""기획서 HTML의 내용으로 15쪽 벡터 PDF를 만든다.

선택적 문서 빌드 의존성: reportlab, Pillow (Agent 실행에는 불필요).
예: python scripts/render_proposal_pdf.py --output dist/애월주민_냄새알림_기획서.pdf
HTML의 data-page, 카드·표·대화·근거 구조를 읽으므로 문구의 별도 사본을 두지 않는다.
"""
from pathlib import Path
from html.parser import HTMLParser
import argparse,re,json,os
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor,Color,white
from reportlab.platypus import Paragraph,Table,TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
W,H=1456,819
INK='#17312C';TEAL='#2F7F86';ORANGE='#BC5A1E';PAPER='#FBFAF6';BG='#EAF1EF';LINE='#D9D4CC';SUB='#52625C'
class Node:
    def __init__(self,tag='',attrs=None,parent=None):self.tag=tag;self.attrs=dict(attrs or []);self.parent=parent;self.children=[]
    def has(self,c):return c in self.attrs.get('class','').split()
    def text(self):
        return re.sub(r'\s+',' ',''.join(x if isinstance(x,str) else ('\n' if x.tag=='br' else x.text()) for x in self.children)).strip()
    def nodes(self,tag=None,cls=None):
        out=[]
        for x in self.children:
            if isinstance(x,Node):
                if (tag is None or x.tag==tag) and (cls is None or x.has(cls)):out.append(x)
                out+=x.nodes(tag,cls)
        return out
    def first(self,tag=None,cls=None):return next(iter(self.nodes(tag,cls)),None)
    def inner(self):
        def rec(n):
            if isinstance(n,str):return escape(n)
            if n.tag=='br':return '<br/>'
            s=''.join(rec(x) for x in n.children)
            if n.tag in ('b','strong'):return '<b>'+s+'</b>'
            return s
        return ''.join(rec(x) for x in self.children)
class Parser(HTMLParser):
    def __init__(self):super().__init__();self.root=Node();self.cur=self.root
    def handle_starttag(self,t,a):
        n=Node(t,a,self.cur);self.cur.children.append(n)
        if t not in ('br','img','meta','link','input','hr','col'):self.cur=n
    def handle_endtag(self,t):
        n=self.cur
        while n.parent is not None:
            if n.tag==t:self.cur=n.parent;return
            n=n.parent
    def handle_data(self,s):self.cur.children.append(s)

def setup_font():
    d=Path(os.environ.get('WINDIR',r'C:\Windows'))/'Fonts'
    regular=d/'malgun.ttf';bold=d/'malgunbd.ttf'
    pdfmetrics.registerFont(TTFont('KR',str(regular)))
    pdfmetrics.registerFont(TTFont('KRB',str(bold)))
    pdfmetrics.registerFontFamily('KR',normal='KR',bold='KRB',italic='KR',boldItalic='KRB')

class Renderer:
    def __init__(self,out):
        self.c=canvas.Canvas(str(out),pagesize=(W,H),pageCompression=1)
        self.c.setTitle('냄새알림 · AI Agent 기획서');self.c.setAuthor('애월주민')
        self.measure=[]
    def rect(self,x,y,w,h,fill=PAPER,stroke=None,r=13):
        c=self.c;c.setFillColor(HexColor(fill));c.setStrokeColor(HexColor(stroke or fill));c.setLineWidth(1)
        c.roundRect(x,y,w,h,r,fill=1,stroke=bool(stroke))
    def p(self,text,x,y,w,size=20,color=INK,bold=False,leading=None,max_h=None):
        style=ParagraphStyle('p',fontName='KRB' if bold else 'KR',fontSize=size,leading=leading or size*1.5,textColor=HexColor(color),wordWrap='CJK',spaceAfter=0)
        p=Paragraph(text,style);_,h=p.wrap(w,2000)
        if max_h and h>max_h+1:raise ValueError(f'Text overflow {h:.1f}>{max_h}: {text[:90]}')
        p.drawOn(self.c,x,y-h);return y-h
    def txt(self,node,x,y,w,**kw):return self.p(node.inner() if node else '',x,y,w,**kw)
    def card(self,node,x,y,w,h,title_size=27,body_size=20):
        self.rect(x,y-h,w,h,stroke=LINE)
        title=node.first('h4') or node.first('h3')
        yy=y-20
        ov=node.first(cls='overline')
        if ov:yy=self.txt(ov,x+22,yy,w-44,size=16,color=TEAL,bold=True)-8
        if title:yy=self.txt(title,x+22,yy,w-44,size=title_size,bold=True)-10
        for n in [x for x in node.children if isinstance(x,Node) and x.tag=='p']:
            yy=self.txt(n,x+22,yy,w-44,size=body_size,color=SUB,max_h=yy-(y-h+15))-7
        return yy
    def gridcards(self,nodes,x,y,w,h,cols=2,gap=20,title_size=27,body_size=20):
        rows=(len(nodes)+cols-1)//cols;cw=(w-gap*(cols-1))/cols;ch=(h-gap*(rows-1))/rows
        for i,n in enumerate(nodes):self.card(n,x+(i%cols)*(cw+gap),y-(i//cols)*(ch+gap),cw,ch,title_size,body_size)
    def table(self,node,x,y,w,widths=None,size=18):
        rows=[]
        for tr in node.nodes('tr'):
            cells=[n for n in tr.children if isinstance(n,Node) and n.tag in ('td','th')]
            style=ParagraphStyle('t',fontName='KR',fontSize=size,leading=size*1.5,textColor=HexColor(INK),wordWrap='CJK')
            rows.append([Paragraph(c.inner(),style) for c in cells])
        t=Table(rows,colWidths=[w*z for z in widths] if widths else [w/len(rows[0])]*len(rows[0]))
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#D5E1DB')),('BACKGROUND',(0,1),(-1,-1),HexColor(PAPER)),('GRID',(0,0),(-1,-1),.7,HexColor('#BCCDC4')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),11),('BOTTOMPADDING',(0,0),(-1,-1),11)]))
        _,h=t.wrap(w,2000);t.drawOn(self.c,x,y-h);return y-h
    def callout(self,node,x,y,w,h,size=20):
        self.rect(x,y-h,w,h,INK);self.txt(node,x+22,y-15,w-44,size=size,color='#F4EFE6',max_h=h-20)
    def image(self,path,x,y,w,h,crop=None):
        im=Image.open(path).convert('RGB')
        if crop:im=im.crop(crop)
        scale=min(w/im.width,h/im.height);iw,ih=im.width*scale,im.height*scale
        self.c.drawImage(ImageReader(im),x+(w-iw)/2,y-ih,width=iw,height=ih,mask='auto')
    def header(self,page,n):
        self.c.setFillColor(HexColor(BG if n>=5 else '#F3E6D8'));self.c.rect(0,0,W,H,fill=1,stroke=0)
        self.c.setFillColor(HexColor(TEAL if n>=5 else ORANGE));self.c.rect(0,H-9,W,9,fill=1,stroke=0)
        self.rect(88,H-79,264,30,TEAL if n>=5 else ORANGE,r=15)
        self.txt(page.first(cls='pill'),102,H-53,245,size=14,color='#FFFFFF',bold=True)
        self.txt(page.first(cls='kicker'),88,H-106,1280,size=18,color=TEAL if n>=5 else ORANGE,bold=True)
        self.txt(page.first('h2'),88,H-151,1280,size=40,bold=True,max_h=112)
        foot=page.first(cls='foot')
        self.txt(foot,88,45,1280,size=13.2,color=SUB,max_h=41)
    def cover(self,p):
        self.c.setFillColor(HexColor(INK));self.c.rect(0,0,W,H,fill=1,stroke=0)
        self.txt(p.first(cls='top'),98,720,1250,size=20,color='#F0A65A',bold=True)
        self.txt(p.first('h1'),98,555,1250,size=110,color='#F4EFE6',bold=True)
        self.txt(p.first(cls='sub'),98,385,1250,size=37,color='#F4EFE6')
        meta=p.first(cls='meta');ds=[x for x in meta.children if isinstance(x,Node)]
        self.txt(ds[0],98,155,1000,size=19,color='#D7DED9');self.txt(ds[1],1200,155,180,size=20,color='#D7DED9')
    def flowcol(self,node,x,y,w,h):
        self.rect(x,y-h,w,h,stroke=LINE)
        yy=y-20;ov=node.first(cls='overline')
        if ov:yy=self.txt(ov,x+20,yy,w-40,size=16,color=TEAL,bold=True)-8
        h3=node.first('h3')
        if h3:yy=self.txt(h3,x+20,yy,w-40,size=25,bold=True)-14
        steps=node.nodes(cls='flowstep')
        for s in steps:
            sh=63 if len(s.text())<55 else 75
            self.rect(x+18,yy-sh,w-36,sh,fill='#F6E4D3' if s.has('em') else '#EDF3F0',r=7)
            self.txt(s,x+31,yy-10,w-62,size=18,max_h=sh-13);yy-=sh+9
        tool=node.first(cls='toolset')
        if tool:self.txt(tool,x+20,yy-5,w-40,size=15,color=SUB,max_h=yy-(y-h+12))
    def page(self,p,n):
        if n==1:self.cover(p);self.c.showPage();return
        self.header(p,n);body=p.first(cls='pagebody');x=88;y=H-230;w=1280
        if n==2:
            hero=body.first(cls='hero');self.rect(x,y-135,w,135,INK)
            self.txt(hero.first(cls='lead'),x+25,y-18,720,size=28,color='#F4EFE6',bold=True)
            stats=hero.nodes(cls='stat')
            for i,st in enumerate(stats):
                xx=x+790+i*235;self.txt(st.first('b'),xx,y-20,225,size=39,color='#F0A65A',bold=True);self.txt(st.first('small'),xx,y-80,220,size=16,color='#D7DED9')
            self.gridcards(body.first(cls='three').nodes(cls='card'),x,y-153,w,148,cols=3,title_size=27,body_size=18)
            ps=[a for a in body.children if isinstance(a,Node) and a.tag=='p']
            self.txt(ps[0],x,y-320,w,size=18,bold=True)
            for h in range(24):self.rect(x+h*w/24,y-385,w/24-3,22,ORANGE if h in {8,9,10,14,15,16,18,19} else '#D9DACD',r=2)
            for h in [0,6,12,18,24]:self.p(f'{h}시',x+min(h,23.1)*w/24,y-391,80,size=14,color=SUB)
            self.txt(ps[-1],x,y-430,w,size=19,color=SUB,max_h=100)
        elif n==3:
            panel=body.first(cls='panel');self.rect(x,y-495,310,495,INK)
            self.txt(panel.first(cls='lab'),x+22,y-20,270,size=17,color='#F0A65A',bold=True)
            for i,row in enumerate(panel.nodes(cls='row')):
                yy=y-90-i*122;self.txt(row.first('b'),x+22,yy,270,size=34,color='#F4EFE6',bold=True);self.txt(row.first('small'),x+22,yy-52,270,size=18,color='#D7DED9')
            cards=body.nodes(cls='card')
            for i,c in enumerate(cards[:2]):
                xx=x+336+i*482;self.rect(xx,y-237,462,237,PAPER,LINE)
                self.txt(c.first(cls='overline'),xx+22,y-17,418,size=16,color=TEAL,bold=True)
                self.txt(c.first(cls='metric'),xx+22,y-62,418,size=55,color=ORANGE,bold=True)
                self.txt(c.first('p'),xx+22,y-148,418,size=18,color=SUB,max_h=78)
            self.gridcards(cards[2:],x+336,y-258,944,237,cols=2,title_size=28,body_size=18)
        elif n==4:
            vals=[12.5,10.9,9.4,23.4,25,18.8,26.1];ns=[64,64,64,64,64,48,23]
            self.txt(body.first(cls='chart-t'),x,y,850,size=19,bold=True)
            bottom=y-365;cw=105
            for i,(v,num) in enumerate(zip(vals,ns)):
                xx=x+12+i*117;hh=v/30*285;self.rect(xx,bottom,cw-20,hh,ORANGE if i==4 else '#9FB5AF',r=3)
                if i==6:
                    self.c.saveState();self.c.setStrokeColor(HexColor('#E7D9C2'));self.c.setLineWidth(4)
                    for d in range(0,int(hh),12):self.c.line(xx,bottom+d,xx+cw-20,min(bottom+d+45,bottom+hh))
                    self.c.restoreState()
                self.p(f'{v:.1f}%',xx,bottom+hh+30,100,size=19,bold=True)
                self.p(str(2020+i)+(' 상' if i==6 else ''),xx-1,bottom-12,115,size=18)
                self.p(f'n={num}',xx,bottom-46,105,size=16,color=SUB)
            self.txt(body.first(cls='smallnote'),x,bottom-90,835,size=17,color=SUB,max_h=90)
            for i,kp in enumerate(body.nodes(cls='kp')):
                yy=y-i*165;self.txt(kp.first('b'),x+890,yy,390,size=30,bold=True,color=ORANGE if i==0 else INK)
                self.txt(kp.first('small'),x+890,yy-65,390,size=19,color=SUB,max_h=95)
        elif n==5:
            for i,col in enumerate(body.nodes(cls='flowcol')):self.flowcol(col,x+i*650,y,630,395)
            self.callout(body.first(cls='callout'),x,y-413,w,103)
        elif n==6:
            chat=body.first(cls='chat');self.rect(x,y-497,520,497,'#BFD0DB')
            self.txt(chat.first(cls='lb'),x+20,y-15,480,size=16,color=SUB,bold=True);yy=y-55
            for b in chat.nodes(cls='bub'):
                isme=b.has('me');bw=350 if isme else 438;xx=x+520-bw-18 if isme else x+18
                style=ParagraphStyle('chat',fontName='KR',fontSize=18,leading=27,wordWrap='CJK');ph=Paragraph(b.inner(),style).wrap(bw-30,1000)[1];hh=ph+22
                self.rect(xx,yy-hh,bw,hh,'#F5DD74' if isme else '#FBFAF6');self.txt(b,xx+15,yy-10,bw-30,size=18);yy-=hh+10
            yy=self.table(body.first('table'),x+552,y,728,[.23,.77],size=18)
            ul=body.first('ul');yy=self.p('<br/>'.join('• '+a.inner() for a in ul.nodes('li')),x+552,yy-18,728,size=19)
            self.txt(body.first(cls='smallnote'),x+552,yy-12,728,size=17,color=SUB,max_h=100)
        elif n==7:
            stages=body.first(cls='stages').nodes(cls='card');cw=302
            for i,s in enumerate(stages):
                xx=x+i*326;fill=ORANGE if i==2 else PAPER;self.rect(xx,y-180,cw,180,fill,LINE if i!=2 else None)
                self.txt(s.first(cls='lv'),xx+17,y-15,cw-34,size=17,color='#FFFFFF' if i==2 else SUB)
                self.txt(s.first('h4'),xx+17,y-48,cw-34,size=29,bold=True,color='#FFFFFF' if i==2 else INK)
                self.txt(s.first('p'),xx+17,y-95,cw-34,size=16.5,color='#FFFFFF' if i==2 else SUB,max_h=78)
            cb=body.first(cls='callbox');self.rect(x,y-384,w,183,INK)
            left=cb.first(cls='l');self.txt(left.first('b'),x+24,y-220,340,size=25,color='#F4EFE6',bold=True)
            self.txt(left.first('small'),x+24,y-310,340,size=17,color='#D7DED9')
            r=cb.first(cls='r');self.rect(x+395,y-365,860,145,PAPER);self.txt(r.first('h6'),x+414,y-235,820,size=17,color=ORANGE,bold=True);self.txt(r.first('p'),x+414,y-267,820,size=19,max_h=93)
            self.txt(body.first(cls='detail'),x,y-408,w,size=19,max_h=120)
        elif n==8:
            self.image(ROOT/'docs/images/05_농장주화면.png',x,y,340,365,crop=(0,0,480,480))
            self.p('점검 요청 → 농장 응답<br/>담당자 화면에 기록',x+15,y-386,320,size=22,bold=True,color=TEAL)
            right=body.first(cls='right');xx=x+390
            self.txt(right.first(cls='flag'),xx,y,890,size=17,color=ORANGE,bold=True)
            note=right.first(cls='notification');self.rect(xx,y-225,890,188,PAPER,LINE)
            self.txt(note.first(cls='overline'),xx+22,y-51,850,size=17,color=TEAL,bold=True)
            raw=''.join(c for c in note.children if isinstance(c,str)).strip()
            self.p(escape(raw),xx+22,y-91,846,size=23)
            for i,b in enumerate(note.first(cls='buttons').nodes('span')):
                self.rect(xx+22+i*290,y-205,275,44,PAPER,TEAL,r=7);self.txt(b,xx+35+i*290,y-171,250,size=18,bold=True,color=TEAL)
            self.txt(note.first(cls='tick'),xx,y-245,890,size=20,color=TEAL,bold=True)
            self.gridcards(right.nodes(cls='card'),xx,y-293,890,140,cols=2,title_size=24,body_size=17)
            self.txt(right.first(cls='smallnote'),xx,y-437,890,size=16,color=SUB,max_h=88)
        elif n==9:
            self.image(ROOT/'docs/images/01_센터화면.png',x,y,785,350)
            self.txt(body.first(cls='smallnote'),x,y-362,785,size=15,color=SUB,max_h=82)
            xx=x+815;self.txt(body.first(cls='flag'),xx,y,465,size=15,color=ORANGE,bold=True)
            cards=body.nodes(cls='card')
            for i,card in enumerate(cards):self.card(card,xx,y-40-i*138,465,128,title_size=21,body_size=16)
            self.callout(body.first(cls='callout'),x,y-446,w,80,size=18)
        elif n==10:
            yy=self.table(body.first('table'),x,y,w,[.23,.55,.22],size=19)
            self.gridcards(body.nodes(cls='card'),x,yy-22,w,180,cols=3,title_size=25,body_size=19)
        elif n==11:
            for i,col in enumerate(body.nodes(cls='flowcol')):self.flowcol(col,x+i*650,y,630,520)
        elif n==12:
            qa=body.first(cls='qa-result');self.rect(x,y-528,830,528,PAPER,LINE)
            xx=x+20;self.txt(qa.first(cls='overline'),xx,y-15,790,size=16,color=TEAL,bold=True)
            yy=self.txt(qa.first(cls='q'),xx,y-48,790,size=24,bold=True)-15
            yy=self.txt(qa.first(cls='answer'),xx,yy,790,size=18)-12
            yy=self.table(qa.first('table'),xx,yy,790,[.48,.34,.18],size=17)-16
            trace=qa.first(cls='trace');self.rect(xx,yy-108,790,108,'#EAF1EF',r=7)
            trace_text=trace.first('b').inner()+'<br/>'+ '<br/>'.join(d.inner() for d in trace.children if isinstance(d,Node) and d.tag=='div')
            self.p(trace_text,xx+15,yy-11,760,size=14.2,max_h=95)
            self.txt(qa.first(cls='smallnote'),xx,yy-122,790,size=14,color=SUB,max_h=50)
            xx=x+858;self.txt(body.first(cls='flag'),xx,y,422,size=16,color=TEAL,bold=True)
            for i,card in enumerate(body.nodes(cls='card')):self.card(card,xx,y-43-i*180,422,168,title_size=25,body_size=18)
            notes=body.nodes(cls='smallnote');self.txt(notes[-1],xx,y-407,422,size=15,color=SUB,max_h=110)
        elif n==13:
            self.callout(body.first(cls='callout'),x,y,w,100)
            yy=self.table(body.first('table'),x,y-118,w,[.23,.35,.42],size=17.5)
            self.txt(body.first(cls='detail'),x,yy-20,w,size=18,color=SUB,max_h=100)
        elif n==14:
            yy=self.table(body.first('table'),x,y,638,[.19,.38,.43],size=17.5)
            cards=body.nodes(cls='card');self.card(cards[0],x,yy-20,638,140,title_size=24,body_size=18)
            self.card(cards[1],x+665,y,615,505,title_size=26,body_size=20)
        elif n==15:
            self.gridcards(body.nodes(cls='card'),x,y,w,424,cols=2,title_size=26,body_size=18)
            self.callout(body.first(cls='callout'),x,y-445,w,80,size=18)
        self.c.showPage()
    def save(self):self.c.save()

def render(output):
    setup_font();p=Parser();p.feed((ROOT/'docs/냄새알림_기획서.html').read_text(encoding='utf-8'))
    pages=p.root.nodes('section',cls='slide');assert len(pages)==15,len(pages)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);r=Renderer(output)
    for i,page in enumerate(pages,1):r.page(page,i)
    r.save();print(f'PDF 15쪽 → {output}')
    return output
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',default=str(ROOT/'dist/애월주민_냄새알림_기획서.pdf'));a=ap.parse_args();render(a.output)
