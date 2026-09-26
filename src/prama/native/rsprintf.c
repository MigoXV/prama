#include "sctk.h"

#ifdef __STDC__
# include <stdarg.h>
#else
# include <varargs.h>
#endif

PRAMA_TLS char static_message_buffer[10000];

#ifdef __STDC__
char *rsprintf(char *format , ...)
#else
char *rsprintf(va_alist)
va_dcl
#endif
{
    va_list args;
#ifndef __STDC__    
    char *format;
#endif

#ifdef __STDC__    
    va_start(args,format);
#else
    va_start(args);
    format = va_arg(args,char *);
#endif
    /*    printf("rsprintf:  format: %s\n",format); */
    int needed = vsnprintf(static_message_buffer, sizeof(static_message_buffer), format, args);
    va_end(args);
    if (needed < 0 || needed >= sizeof(static_message_buffer)){
      fprintf(stderr,"Error: rsprintf's internal buffer is too small.  increase the size\n");
      exit (1);
    }
    /*    printf("rsprintf:  message: %s\n",static_message_buffer);*/
    return(static_message_buffer);
}

