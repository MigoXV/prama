#include "bridge.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *read_file(const char *root,const char *name) {
    char path[4096];snprintf(path,sizeof(path),"%s/%s",root,name);
    FILE *fp=fopen(path,"rb");assert(fp);
    assert(!fseek(fp,0,SEEK_END));long n=ftell(fp);assert(n>=0);rewind(fp);
    char *text=malloc((size_t)n+1);assert(text);
    assert(fread(text,1,n,fp)==(size_t)n);text[n]=0;fclose(fp);return text;
}
static int notify(void *cancel,ScliteResult *r,int g,int u) {
    ScliteUtterance row;assert(!sclite_result_utterance(r,g,u,&row));
    for(int i=0;i<row.token_count;i++) { ScliteToken t;assert(!sclite_result_token(r,g,u,i,&t)); }
    return *(int *)cancel;
}
int main(int argc,char **argv) {
    assert(argc==2);const char *root=argv[1];
    ScliteContext *c=sclite_context_new();assert(c);
    for(int mode=0;mode<10;mode++) {
        const char *rn="tests.ref", *hn="tests.hyp";int rf=1,hf=1;
        ScliteOptions o;sclite_options_init(&o);o.encoding="UTF-8";
        char path[4096];
        if(mode<3) {
            o.infer_word_seg=mode;
            if(mode) { snprintf(path,sizeof(path),"%s/tests.lex",root);o.lexicon_path=path;o.infer_flags=1; }
            else { o.optional_deletion=1;o.fragment_correct=1; }
        } else if(mode==3) {
            rn="csrnab.ref";hn="csrnab.hyp";o.id_type=1;
            snprintf(path,sizeof(path),"%s/csrnab_r.wwl",root);o.wwl_path=path;
        } else if(mode<8) {
            rn=mode==4 ? "lvc_refe.stm" : "lvc_ref.stm";hn="lvc_hypc.ctm";rf=2;hf=3;
            if(mode==5) o.char_align_flags=1;
            if(mode==6) o.reduce_ref_segments=o.reduce_hyp_words=1;
            if(mode==7) o.left_to_right=0;
        } else {
            rn="lvc_hyp.ctm";hn="lvc_hypc.ctm";rf=hf=3;o.time_align=mode==9;
        }
        char *ref=read_file(root,rn),*hyp=read_file(root,hn);
        for(int cancel=0;cancel<2;cancel++) {
            ScliteResult *r=NULL;
            int rc=sclite_align_texts_stream(c,ref,strlen(ref),rf,hyp,strlen(hyp),hf,&o,notify,&cancel,&r);
            if(cancel) { assert(rc && !r); continue; }
            if(rc) fprintf(stderr,"mode %d failed: %s\n",mode,sclite_context_error(c));
            assert(!rc && r);
            for(int type=1;type<=5;type++) {
                char *text;size_t size;
                assert(!sclite_result_report_text(c,r,type,&text,&size));assert(size);sclite_free_string(text);
            }
            sclite_result_free(r);
        }
        free(ref);free(hyp);
    }
    sclite_context_free(c);puts("10 upstream format/option cases: reports, callbacks and cancellation passed");
}
