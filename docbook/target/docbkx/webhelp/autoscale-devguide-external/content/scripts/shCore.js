function highlightCode(a){var b=a.target;null==b&&(b=a.srcElement);var c=findParentElement(b,".syntaxhighlighter"),d=findContainerElement(b),e=document.createElement("textarea"),f,g=getHighlighterId(c.id);f=document.getElementById(g),addClass(c,"source");var h=d.childNodes,i=[];for(var j=0;j<h.length;j++)i.push(h[j].innerText||h[j].textContent);i=i.join("\r"),i=i.replace(/\u00a0/g," "),e.appendChild(document.createTextNode(i)),d.appendChild(e),e.focus(),e.select(),d.addEventListener?d.addEventListener("click",function(){removeHighlight(e,c)},!1):d.attachEvent&&d.attachEvent("onmouseup",function(){removeHighlight(e,c)},!1)}function removeHighlight(a,b){a.parentNode.removeChild(a),removeClass(b,"source")}function findContainerElement(a){var b=findParentElement(a,".syntaxhighlighter"),c=null;if(null!=b&&b!=undefined){var d=b.getElementsByTagName("div");if(null!=d&&d!=undefined&&d.length>0){var e=0,f=null;for(e=0;e<d.length;++e){f=d[e];if(f.className=="container"){c=f;break}}}}return c}function findElement(a,b,c){if(a==null)return null;var d=c!=1?a.childNodes:[a.parentNode],e={"#":"id",".":"className"}[b.substr(0,1)]||"nodeName",f,g;f=e!="nodeName"?b.substr(1):b.toUpperCase();if((a[e]||"").indexOf(f)!=-1)return a;for(var h=0;d&&h<d.length&&g==null;h++)g=findElement(d[h],b,c);return g}function findParentElement(a,b){return findElement(a,b,!0)}function getHighlighterId(a){var b="highlighter_";return a.indexOf(b)==0?a:b+a}function addClass(a,b){hasClass(a,b)||(a.className+=" "+b)}function hasClass(a,b){return a.className.indexOf(b)!=-1}function removeClass(a,b){a.className=a.className.replace(b,"")}var XRegExp;if(XRegExp)throw Error("can't load XRegExp twice in the same frame");(function(a){function l(a,b){if(!XRegExp.isRegExp(a))throw TypeError("type RegExp expected");var c=a._xregexp;return a=XRegExp(a.source,m(a)+(b||"")),c&&(a._xregexp={source:c.source,captureNames:c.captureNames?c.captureNames.slice(0):null}),a}function m(a){return(a.global?"g":"")+(a.ignoreCase?"i":"")+(a.multiline?"m":"")+(a.extended?"x":"")+(a.sticky?"y":"")}function n(a,b,c,d){var g=f.length,h,i,j;e=!0;try{while(g--){j=f[g];if(c&j.scope&&(!j.trigger||j.trigger.call(d))){j.pattern.lastIndex=b,i=j.pattern.exec(a);if(i&&i.index===b){h={output:j.handler.call(d,i,c),match:i};break}}}}catch(k){throw k}finally{e=!1}return h}function o(a,b,c){if(Array.prototype.indexOf)return a.indexOf(b,c);for(var d=c||0;d<a.length;d++)if(a[d]===b)return d;return-1}XRegExp=function(b,d){var f=[],h=XRegExp.OUTSIDE_CLASS,i=0,j,m,o,p,q;if(XRegExp.isRegExp(b)){if(d!==a)throw TypeError("can't supply flags when constructing one RegExp from another");return l(b)}if(e)throw Error("can't call the XRegExp constructor within token definition functions");d=d||"",j={hasNamedCapture:!1,captureNames:[],hasFlag:function(a){return d.indexOf(a)>-1},setFlag:function(a){d+=a}};while(i<b.length)m=n(b,i,h,j),m?(f.push(m.output),i+=m.match[0].length||1):(o=g.exec.call(k[h],b.slice(i)))?(f.push(o[0]),i+=o[0].length):(p=b.charAt(i),p==="["?h=XRegExp.INSIDE_CLASS:p==="]"&&(h=XRegExp.OUTSIDE_CLASS),f.push(p),i++);return q=RegExp(f.join(""),g.replace.call(d,c,"")),q._xregexp={source:b,captureNames:j.hasNamedCapture?j.captureNames:null},q},XRegExp.version="1.5.1",XRegExp.INSIDE_CLASS=1,XRegExp.OUTSIDE_CLASS=2;var b=/\$(?:(\d\d?|[$&`'])|{([$\w]+)})/g,c=/[^gimy]+|([\s\S])(?=[\s\S]*\1)/g,d=/^(?:[?*+]|{\d+(?:,\d*)?})\??/,e=!1,f=[],g={exec:RegExp.prototype.exec,test:RegExp.prototype.test,match:String.prototype.match,replace:String.prototype.replace,split:String.prototype.split},h=g.exec.call(/()??/,"")[1]===a,i=function(){var a=/^/g;return g.test.call(a,""),!a.lastIndex}(),j=RegExp.prototype.sticky!==a,k={};k[XRegExp.INSIDE_CLASS]=/^(?:\\(?:[0-3][0-7]{0,2}|[4-7][0-7]?|x[\dA-Fa-f]{2}|u[\dA-Fa-f]{4}|c[A-Za-z]|[\s\S]))/,k[XRegExp.OUTSIDE_CLASS]=/^(?:\\(?:0(?:[0-3][0-7]{0,2}|[4-7][0-7]?)?|[1-9]\d*|x[\dA-Fa-f]{2}|u[\dA-Fa-f]{4}|c[A-Za-z]|[\s\S])|\(\?[:=!]|[?*+]\?|{\d+(?:,\d*)?}\??)/,XRegExp.addToken=function(a,b,c,d){f.push({pattern:l(a,"g"+(j?"y":"")),handler:b,scope:c||XRegExp.OUTSIDE_CLASS,trigger:d||null})},XRegExp.cache=function(a,b){var c=a+"/"+(b||"");return XRegExp.cache[c]||(XRegExp.cache[c]=XRegExp(a,b))},XRegExp.copyAsGlobal=function(a){return l(a,"g")},XRegExp.escape=function(a){return a.replace(/[-[\]{}()*+?.,\\^$|#\s]/g,"\\$&")},XRegExp.execAt=function(a,b,c,d){var e=l(b,"g"+(d&&j?"y":"")),f;return e.lastIndex=c=c||0,f=e.exec(a),d&&f&&f.index!==c&&(f=null),b.global&&(b.lastIndex=f?e.lastIndex:0),f},XRegExp.freezeTokens=function(){XRegExp.addToken=function(){throw Error("can't run addToken after freezeTokens")}},XRegExp.isRegExp=function(a){return Object.prototype.toString.call(a)==="[object RegExp]"},XRegExp.iterate=function(a,b,c,d){var e=l(b,"g"),f=-1,g;while(g=e.exec(a))b.global&&(b.lastIndex=e.lastIndex),c.call(d,g,++f,a,b),e.lastIndex===g.index&&e.lastIndex++;b.global&&(b.lastIndex=0)},XRegExp.matchChain=function(a,b){return function c(a,d){var e=b[d].regex?b[d]:{regex:b[d]},f=l(e.regex,"g"),g=[],h;for(h=0;h<a.length;h++)XRegExp.iterate(a[h],f,function(a){g.push(e.backref?a[e.backref]||"":a[0])});return d===b.length-1||!g.length?g:c(g,d+1)}([a],0)},RegExp.prototype.apply=function(a,b){return this.exec(b[0])},RegExp.prototype.call=function(a,b){return this.exec(b)},RegExp.prototype.exec=function(b){var c,d,e,f;this.global||(f=this.lastIndex),c=g.exec.apply(this,arguments);if(c){!h&&c.length>1&&o(c,"")>-1&&(e=RegExp(this.source,g.replace.call(m(this),"g","")),g.replace.call((b+"").slice(c.index),e,function(){for(var b=1;b<arguments.length-2;b++)arguments[b]===a&&(c[b]=a)}));if(this._xregexp&&this._xregexp.captureNames)for(var j=1;j<c.length;j++)d=this._xregexp.captureNames[j-1],d&&(c[d]=c[j]);!i&&this.global&&!c[0].length&&this.lastIndex>c.index&&this.lastIndex--}return this.global||(this.lastIndex=f),c},RegExp.prototype.test=function(a){var b,c;return this.global||(c=this.lastIndex),b=g.exec.call(this,a),b&&!i&&this.global&&!b[0].length&&this.lastIndex>b.index&&this.lastIndex--,this.global||(this.lastIndex=c),!!b},String.prototype.match=function(a){XRegExp.isRegExp(a)||(a=RegExp(a));if(a.global){var b=g.match.apply(this,arguments);return a.lastIndex=0,b}return a.exec(this)},String.prototype.replace=function(a,c){var d=XRegExp.isRegExp(a),e,f,h,i;return d?(a._xregexp&&(e=a._xregexp.captureNames),a.global||(i=a.lastIndex)):a+="",Object.prototype.toString.call(c)==="[object Function]"?f=g.replace.call(this+"",a,function(){if(e){arguments[0]=new String(arguments[0]);for(var b=0;b<e.length;b++)e[b]&&(arguments[0][e[b]]=arguments[b+1])}return d&&a.global&&(a.lastIndex=arguments[arguments.length-2]+arguments[0].length),c.apply(null,arguments)}):(h=this+"",f=g.replace.call(h,a,function(){var a=arguments;return g.replace.call(c+"",b,function(b,c,d){if(!c){var g=+d;return g<=a.length-3?a[g]:(g=e?o(e,d):-1,g>-1?a[g+1]:b)}switch(c){case"$":return"$";case"&":return a[0];case"`":return a[a.length-1].slice(0,a[a.length-2]);case"'":return a[a.length-1].slice(a[a.length-2]+a[0].length);default:var f="";c=+c;if(!c)return b;while(c>a.length-3)f=String.prototype.slice.call(c,-1)+f,c=Math.floor(c/10);return(c?a[c]||"":"$")+f}})})),d&&(a.global?a.lastIndex=0:a.lastIndex=i),f},String.prototype.split=function(b,c){if(!XRegExp.isRegExp(b))return g.split.apply(this,arguments);var d=this+"",e=[],f=0,h,i;if(c===a||+c<0)c=Infinity;else{c=Math.floor(+c);if(!c)return[]}b=XRegExp.copyAsGlobal(b);while(h=b.exec(d)){if(b.lastIndex>f){e.push(d.slice(f,h.index)),h.length>1&&h.index<d.length&&Array.prototype.push.apply(e,h.slice(1)),i=h[0].length,f=b.lastIndex;if(e.length>=c)break}b.lastIndex===h.index&&b.lastIndex++}return f===d.length?(!g.test.call(b,"")||i)&&e.push(""):e.push(d.slice(f)),e.length>c?e.slice(0,c):e},XRegExp.addToken(/\(\?#[^)]*\)/,function(a){return g.test.call(d,a.input.slice(a.index+a[0].length))?"":"(?:)"}),XRegExp.addToken(/\((?!\?)/,function(){return this.captureNames.push(null),"("}),XRegExp.addToken(/\(\?<([$\w]+)>/,function(a){return this.captureNames.push(a[1]),this.hasNamedCapture=!0,"("}),XRegExp.addToken(/\\k<([\w$]+)>/,function(a){var b=o(this.captureNames,a[1]);return b>-1?"\\"+(b+1)+(isNaN(a.input.charAt(a.index+a[0].length))?"":"(?:)"):a[0]}),XRegExp.addToken(/\[\^?]/,function(a){return a[0]==="[]"?"\\b\\B":"[\\s\\S]"}),XRegExp.addToken(/^\(\?([imsx]+)\)/,function(a){return this.setFlag(a[1]),""}),XRegExp.addToken(/(?:\s+|#.*)+/,function(a){return g.test.call(d,a.input.slice(a.index+a[0].length))?"":"(?:)"},XRegExp.OUTSIDE_CLASS,function(){return this.hasFlag("x")}),XRegExp.addToken(/\./,function(){return"[\\s\\S]"},XRegExp.OUTSIDE_CLASS,function(){return this.hasFlag("s")})})();if(typeof SyntaxHighlighter=="undefined")var SyntaxHighlighter=function(){function b(a){var b=[];for(var c=0;c<a.length;c++)b.push(a[c]);return b}function c(a){return a.split(/\r?\n/)}function d(b){return a.vars.highlighters[getHighlighterId(b)]}function e(a){return document.getElementById(getHighlighterId(a))}function f(b){a.vars.highlighters[getHighlighterId(b.id)]=b}function g(a,b,c){c=Math.max(c||0,0);for(var d=c;d<a.length;d++)if(a[d]==b)return d;return-1}function h(a){return(a||"")+Math.round(Math.random()*1e6).toString()}function i(a,b){var c={},d;for(d in a)c[d]=a[d];for(d in b)c[d]=b[d];return c}function j(a){var b={"true":!0,"false":!1}[a];return b==null?a:b}function k(a,b,c,d,e){var f=(screen.width-c)/2,g=(screen.height-d)/2;e+=", left="+f+", top="+g+", width="+c+", height="+d,e=e.replace(/^,/,"");var h=window.open(a,b,e);return h.focus(),h}function l(a,b,c,d){function e(a){a=a||window.event,a.target||(a.target=a.srcElement,a.preventDefault=function(){this.returnValue=!1}),c.call(d||window,a)}a.attachEvent?a.attachEvent("on"+b,e):a.addEventListener(b,e,!1)}function m(b){window.alert(a.config.strings.alert+b)}function n(b,c){var d=a.vars.discoveredBrushes,e=null;if(d==null){d={};for(var f in a.brushes){var g=a.brushes[f],h=g.aliases;if(h==null)continue;g.brushName=f.toLowerCase();for(var i=0;i<h.length;i++)d[h[i]]=f}a.vars.discoveredBrushes=d}return e=a.brushes[d[b]],e==null&&c&&m(a.config.strings.noBrush+b),e}function o(a,b){var d=c(a);for(var e=0;e<d.length;e++)d[e]=b(d[e],e);return d.join("\r\n")}function p(a){return a.replace(/^[ ]*[\n]+|[\n]*[ ]*$/g,"")}function q(a){var b,c={},d=new XRegExp("^\\[(?<values>(.*?))\\]$"),e=new XRegExp("(?<name>[\\w-]+)\\s*:\\s*(?<value>[\\w-%#]+|\\[.*?\\]|\".*?\"|'.*?')\\s*;?","g");while((b=e.exec(a))!=null){var f=b.value.replace(/^['"]|['"]$/g,"");if(f!=null&&d.test(f)){var g=d.exec(f);f=g.values.length>0?g.values.split(/\s*,\s*/):[]}c[b.name]=f}return c}function r(b,c){return b==null||b.length==0||b=="\n"?b:(b=b.replace(/</g,"&lt;"),b=b.replace(/ {2,}/g,function(b){var c="";for(var d=0;d<b.length-1;d++)c+=a.config.space;return c+" "}),c!=null&&(b=o(b,function(a){if(a.length==0)return"";var b="";return a=a.replace(/^(&nbsp;| )+/,function(a){return b=a,""}),a.length==0?b:b+'<code class="'+c+'">'+a+"</code>"})),b)}function s(a,b){var c=a.toString();while(c.length<b)c="0"+c;return c}function t(a,b){var c="";for(var d=0;d<b;d++)c+=" ";return a.replace(/\t/g,c)}function u(a,b){function h(a,b,c){return a.substr(0,b)+f.substr(0,c)+a.substr(b+1,a.length)}var d=c(a),e="	",f="";for(var g=0;g<50;g++)f+="                    ";return a=o(a,function(a){if(a.indexOf(e)==-1)return a;var c=0;while((c=a.indexOf(e))!=-1){var d=b-c%b;a=h(a,c,d)}return a}),a}function v(b){var c=/<br\s*\/?>|&lt;br\s*\/?&gt;/gi;return a.config.bloggerMode==1&&(b=b.replace(c,"\n")),a.config.stripBrs==1&&(b=b.replace(c,"")),b}function w(a){return a.replace(/^\s+|\s+$/g,"")}function x(a){var b=c(v(a)),d=new Array,e=/^\s*/,f=1e3;for(var g=0;g<b.length&&f>0;g++){var h=b[g];if(w(h).length==0)continue;var i=e.exec(h);if(i==null)return a;f=Math.min(i[0].length,f)}if(f>0)for(var g=0;g<b.length;g++)b[g]=b[g].substr(f);return b.join("\n")}function y(a,b){return a.index<b.index?-1:a.index>b.index?1:a.length<b.length?-1:a.length>b.length?1:0}function z(b,c){function d(a,b){return a[0]}var e=0,f=null,g=[],h=c.func?c.func:d;while((f=c.regex.exec(b))!=null){var i=h(f,c);typeof i=="string"&&(i=[new a.Match(i,f.index,c.css)]),g=g.concat(i)}return g}function A(b){var c=/(.*)((&gt;|&lt;).*)/;return b.replace(a.regexLib.url,function(a){var b="",d=null;if(d=c.exec(a))a=d[1],b=d[2];return'<a href="'+a+'">'+a+"</a>"+b})}function B(){var a=document.getElementsByTagName("script"),b=[];for(var c=0;c<a.length;c++)a[c].type=="syntaxhighlighter"&&b.push(a[c]);return b}function C(a){var b="<![CDATA[",c="]]>",d=w(a),e=!1,f=b.length,g=c.length;d.indexOf(b)==0&&(d=d.substring(f),e=!0);var h=d.length;return d.indexOf(c)==h-g&&(d=d.substring(0,h-g),e=!0),e?d:a}function D(a){var b=a.target,c=findParentElement(b,".syntaxhighlighter"),e=findParentElement(b,".container"),f=document.createElement("textarea"),g;if(!e||!c||findElement(e,"textarea"))return;g=d(c.id),addClass(c,"source");var h=e.childNodes,i=[];for(var j=0;j<h.length;j++)i.push(h[j].innerText||h[j].textContent);i=i.join("\r"),i=i.replace(/\u00a0/g," "),f.appendChild(document.createTextNode(i)),e.appendChild(f),f.focus(),f.select(),l(f,"blur",function(a){f.parentNode.removeChild(f),removeClass(c,"source")})}function E(a,b){var c=a.target,d=c.className,e=0,f=d.indexOf("syntaxhighlighter");while(-1==f&&e<10)++e,c=c.parentNode,d=c.className,f=d.indexOf("syntaxhighlighter");if(f==0){f=-1;var g=c.getElementsByTagName("div");if(null!=g&&g.length>0){e=0;for(e=0;e<g.length;++e){c=g[e],d=c.className,f=d.indexOf(b);if(c.className!=null&&f!=-1)break}}}return f==-1&&(c=null),c}function F(a){var b=E(a,"mytoolbar");null!=b&&(b.className="show")}function G(a){var b=E(a,"show");null!=b&&(b.className="mytoolbar")}typeof require!="undefined"&&typeof XRegExp=="undefined"&&(XRegExp=require("XRegExp").XRegExp);var a={defaults:{"class-name":"","first-line":1,"pad-line-numbers":!1,highlight:null,title:null,"smart-tabs":!0,"tab-size":4,gutter:!0,toolbar:!0,"quick-code":!0,collapse:!1,"auto-links":!1,light:!1,unindent:!0,"html-script":!1},config:{space:"&nbsp;",useScriptTags:!0,bloggerMode:!1,stripBrs:!1,tagName:"pre",strings:{expandSource:"expand source",help:"?",alert:"SyntaxHighlighter\n\n",noBrush:"Can't find brush for: ",brushNotHtmlScript:"Brush wasn't configured for html-script option: ",aboutDialog:"@ABOUT@"}},vars:{discoveredBrushes:null,highlighters:{}},brushes:{},regexLib:{multiLineCComments:/\/\*[\s\S]*?\*\//gm,singleLineCComments:/\/\/.*$/gm,singleLinePerlComments:/#.*$/gm,doubleQuotedString:/"([^\\"\n]|\\.)*"/g,singleQuotedString:/'([^\\'\n]|\\.)*'/g,multiLineDoubleQuotedString:new XRegExp('"([^\\\\"]|\\\\.)*"',"gs"),multiLineSingleQuotedString:new XRegExp("'([^\\\\']|\\\\.)*'","gs"),xmlComments:/(&lt;|<)!--[\s\S]*?--(&gt;|>)/gm,url:/\w+:\/\/[\w-.\/?%&=:@;#]*/g,phpScriptTags:{left:/(&lt;|<)\?(?:=|php)?/g,right:/\?(&gt;|>)/g,eof:!0},aspScriptTags:{left:/(&lt;|<)%=?/g,right:/%(&gt;|>)/g},scriptScriptTags:{left:/(&lt;|<)\s*script.*?(&gt;|>)/gi,right:/(&lt;|<)\/\s*script\s*(&gt;|>)/gi}},toolbar:{getHtml:function(b){function f(b,c){return a.toolbar.getButtonHtml(b,c,a.config.strings[c])}var c='<div class="show">',d=a.toolbar.items,e=d.list;for(var g=0;g<e.length;g++)c+=(d[e[g]].getHtml||f)(b,e[g]);return c+="</div>",c},getButtonHtml:function(a,b,c){return'<div class="newtoolbar2"> <img src="images/icon_clipboard.png" alt="Select Text" title="Select Text" height="20" width="20" align="right" onclick="highlightCode(event);" /> </div>'},handler:function(b){function f(a){var b=new RegExp(a+"_(\\w+)"),c=b.exec(e);return c?c[1]:null}var c=b.target,e=c.className||"",g=d(findParentElement(c,".syntaxhighlighter").id),h=f("command");g&&h&&a.toolbar.items[h].execute(g),b.preventDefault()},items:{list:["expandSource","help"],expandSource:{getHtml:function(b){if(b.getParam("collapse")!=1)return"";var c=b.getParam("title");return a.toolbar.getButtonHtml(b,"expandSource",c?c:a.config.strings.expandSource)},execute:function(a){var b=e(a.id);removeClass(b,"collapsed")}},help:{execute:function(b){var c=k("","_blank",500,250,"scrollbars=0"),d=c.document;d.write(a.config.strings.aboutDialog),d.close(),c.focus()}}}},findElements:function(c,d){var e=d?[d]:b(document.getElementsByTagName(a.config.tagName)),f=a.config,g=[];f.useScriptTags&&(e=e.concat(B()));if(e.length===0)return g;for(var h=0;h<e.length;h++){var j={target:e[h],params:i(c,q(e[h].className))};if(j.params["brush"]==null)continue;g.push(j)}return g},highlight:function(b,c){var d=this.findElements(b,c),e="innerHTML",f=null,g=a.config;if(d.length===0)return;for(var h=0;h<d.length;h++){var c=d[h],i=c.target,j=c.params,k=j.brush,l;if(k==null)continue;if(j["html-script"]=="true"||a.defaults["html-script"]==1)f=new a.HtmlScript(k),k="htmlscript";else{var m=n(k);if(!m)continue;f=new m}l=i[e],g.useScriptTags&&(l=C(l)),(i.title||"")!=""&&(j.title=i.title),j.brush=k,f.init(j),c=f.getDiv(l),(i.id||"")!=""&&(c.id=i.id),i.parentNode.replaceChild(c,i)}},all:function(b){l(window,"load",function(){a.highlight(b)})}};return a.Match=function(a,b,c){this.value=a,this.index=b,this.length=a.length,this.css=c,this.brushName=null},a.Match.prototype.toString=function(){return this.value},a.HtmlScript=function(b){function j(a,b){for(var c=0;c<a.length;c++)a[c].index+=b}function k(a,b){var e=a.code,f=[],g=d.regexList,h=a.index+a.left.length,i=d.htmlScript,k;for(var l=0;l<g.length;l++)k=z(e,g[l]),j(k,h),f=f.concat(k);i.left!=null&&a.left!=null&&(k=z(a.left,i.left),j(k,a.index),f=f.concat(k)),i.right!=null&&a.right!=null&&(k=z(a.right,i.right),j(k,a.index+a[0].lastIndexOf(a.right)),f=f.concat(k));for(var m=0;m<f.length;m++)f[m].brushName=c.brushName;return f}var c=n(b),d,e=new a.brushes.Xml,f=null,g=this,h="getDiv getHtml init".split(" ");if(c==null)return;d=new c;for(var i=0;i<h.length;i++)(function(){var a=h[i];g[a]=function(){return e[a].apply(e,arguments)}})();if(d.htmlScript==null){m(a.config.strings.brushNotHtmlScript+b);return}e.regexList.push({regex:d.htmlScript.code,func:k})},a.Highlighter=function(){},a.Highlighter.prototype={getParam:function(a,b){var c=this.params[a];return j(c==null?b:c)},create:function(a){return document.createElement(a)},findMatches:function(a,b){var c=[];if(a!=null)for(var d=0;d<a.length;d++)typeof a[d]=="object"&&(c=c.concat(z(b,a[d])));return this.removeNestedMatches(c.sort(y))},removeNestedMatches:function(a){for(var b=0;b<a.length;b++){if(a[b]===null)continue;var c=a[b],d=c.index+c.length;for(var e=b+1;e<a.length&&a[b]!==null;e++){var f=a[e];if(f===null)continue;if(f.index>d)break;f.index==c.index&&f.length>c.length?a[b]=null:f.index>=c.index&&f.index<d&&(a[e]=null)}}return a},figureOutLineNumbers:function(a){var b=[],c=parseInt(this.getParam("first-line"));return o(a,function(a,d){b.push(d+c)}),b},isLineHighlighted:function(a){var b=this.getParam("highlight",[]);return typeof b!="object"&&b.push==null&&(b=[b]),g(b,a.toString())!=-1},getLineHtml:function(a,b,c){var d=["line","number"+b,"index"+a,"alt"+(b%2==0?1:2).toString()];return this.isLineHighlighted(b)&&d.push("highlighted"),b==0&&d.push("break"),'<div class="'+d.join(" ")+'">'+c+"</div>"},getLineNumbersHtml:function(b,d){var e="",f=c(b).length,g=parseInt(this.getParam("first-line")),h=this.getParam("pad-line-numbers");h==1?h=(g+f-1).toString().length:isNaN(h)==1&&(h=0);for(var i=0;i<f;i++){var j=d?d[i]:g+i,b=j==0?a.config.space:s(j,h);e+=this.getLineHtml(i,j,b)}return e},getCodeLinesHtml:function(b,d){b=w(b);var e=c(b),f=this.getParam("pad-line-numbers"),g=parseInt(this.getParam("first-line")),b="",h=this.getParam("brush");for(var i=0;i<e.length;i++){var j=e[i],k=/^(&nbsp;|\s)+/.exec(j),l=null,m=d?d[i]:g+i;k!=null&&(l=k[0].toString(),j=j.substr(l.length),l=l.replace(" ",a.config.space)),j=w(j),j.length==0&&(j=a.config.space),b+=this.getLineHtml(i,m,(l!=null?'<code class="'+h+' spaces">'+l+"</code>":"")+j)}return b},getTitleHtml:function(a){return a?"<caption>"+a+"</caption>":""},getMatchesHtml:function(a,b){function f(a){var b=a?a.brushName||e:e;return b?b+" ":""}var c=0,d="",e=this.getParam("brush","");for(var g=0;g<b.length;g++){var h=b[g],i;if(h===null||h.length===0)continue;i=f(h),d+=r(a.substr(c,h.index-c),i+"plain")+r(h.value,i+h.css),c=h.index+h.length+(h.offset||0)}return d+=r(a.substr(c),f()+"plain"),d},getHtml:function(b){var c="",d=["syntaxhighlighter"],e,f,g;return b=b.replace(/<span(.)+?(alt\=\(([0-9]?[0-9])\))??(.)+?callouts\/([0-9]?[0-9])\.png\"(\salt\=\(([0-9]?[0-9])\))??(.)+?<\/span>/ig,"@@@@$5@$5@@@@"),b=b.replace(/<a(\s)+?id(\s)*?=(.)+?<img(.)+?\/callouts\/([0-9]?[0-9])\.png(.)+?>/ig,"~~~~$5~$5~~~~"),b=b.replace(/<span\s+?class\s*?\=\s*?(\")??bold(\")??(.|\n|\r|\f)+?<strong>(.+?)<\/strong>(.)*?<\/span>/ig,"!!!!$4!!!!"),this.getParam("light")==1&&(this.params.toolbar=this.params.gutter=!1),className="syntaxhighlighter",this.getParam("collapse")==1&&d.push("collapsed"),(gutter=this.getParam("gutter"))==0&&d.push("nogutter"),d.push(this.getParam("class-name")),d.push(this.getParam("brush")),b=p(b).replace(/\r/g," "),e=this.getParam("tab-size"),b=this.getParam("smart-tabs")==1?u(b,e):t(b,e),this.getParam("unindent")&&(b=x(b)),gutter&&(g=this.figureOutLineNumbers(b)),f=this.findMatches(this.regexList,b),c=this.getMatchesHtml(b,f),c=this.getCodeLinesHtml(c,g),this.getParam("auto-links")&&(c=A(c)),typeof navigator!="undefined"&&navigator.userAgent&&navigator.userAgent.match(/MSIE/)&&d.push("ie"),c='<div id="'+getHighlighterId(this.id)+'" class="'+d.join(" ")+'">'+(this.getParam("toolbar")?a.toolbar.getHtml(this):"")+'<table border="0" cellpadding="0" cellspacing="0">'+this.getTitleHtml(this.getParam("title"))+"<tbody>"+"<tr>"+(gutter?'<td class="gutter">'+this.getLineNumbersHtml(b)+"</td>":"")+'<td class="code">'+'<div class="container">'+c+"</div>"+"</td>"+"</tr>"+"</tbody>"+"</table>"+"</div>",c=c.replace(/@@@@([0-9]?[0-9])@([0-9]?[0-9])@@@@/g,'<span class="co"><img src="../common/images/callouts/$1.png" alt="($2)"/></span>'),c=c.replace(/~~~~([0-9]?[0-9])~([0-9]?[0-9])~~~~/g,'<span class="co"><img src="../common/images/callouts/$1.png" alt="($2)"/></span>'),c=c.replace(/!!!!(.+?)!!!!/g,'<span class="bold variable">$1</span>'),c},getDiv:function(b){b===null&&(b=""),this.code=b;var c=this.create("div");return c.innerHTML=this.getHtml(b),this.getParam("toolbar")&&l(findElement(c,".toolbar"),"click",a.toolbar.handler),this.getParam("quick-code")&&l(findElement(c,".code"),"dblclick",D),c},init:function(b){this.id=h(),f(this),this.params=i(a.defaults,b||{}),this.getParam("light")==1&&(this.params.toolbar=this.params.gutter=!1)},getKeywords:function(a){return a=a.replace(/^\s+|\s+$/g,"").replace(/\s+/g,"|"),"\\b(?:"+a+")\\b"},forHtmlScript:function(a){var b={end:a.right.source};a.eof&&(b.end="(?:(?:"+b.end+")|$)"),this.htmlScript={left:{regex:a.left,css:"script"},right:{regex:a.right,css:"script"},code:new XRegExp("(?<left>"+a.left.source+")"+"(?<code>.*?)"+"(?<right>"+b.end+")","sgi")}}},a}();typeof exports!="undefined"?exports.SyntaxHighlighter=SyntaxHighlighter:null

;(function()
{
	// CommonJS
	SyntaxHighlighter = SyntaxHighlighter || (typeof require !== 'undefined'? require('shCore').SyntaxHighlighter : null);

	function Brush()
	{
		var keywords =	'if fi then elif else for do done until while break continue case esac function return in eq ne ge le';
		var commands =  'alias apropos awk basename bash bc bg builtin bzip2 cal cat cd cfdisk chgrp chmod chown chroot' +
						'cksum clear cmp comm command cp cron crontab csplit curl cut date dc dd ddrescue declare df ' +
						'diff diff3 dig dir dircolors dirname dirs du echo egrep eject enable env ethtool eval ' +
						'exec exit expand export expr false fdformat fdisk fg fgrep file find fmt fold format ' +
						'free fsck ftp gawk getopts grep groups gzip hash head history hostname id ifconfig ' +
						'import install join kill less let ln local locate logname logout look lpc lpr lprint ' +
						'lprintd lprintq lprm ls lsof make man mkdir mkfifo mkisofs mknod more mount mtools ' +
						'mv netstat nice nl nohup nslookup open op passwd paste pathchk ping popd pr printcap ' +
						'printenv printf ps pushd pwd quota quotacheck quotactl ram rcp read readonly renice ' +
						'remsync rm rmdir rsync screen scp sdiff sed select seq set sftp shift shopt shutdown ' +
						'sleep sort source split ssh strace su sudo sum symlink sync tail tar tee test time ' +
						'times touch top traceroute trap tr true tsort tty ulimit umask umount unalias ' +
						'uname unexpand uniq units unset unshar useradd usermod users uuencode uudecode v vdir ' +
						'vi watch wc whereis which who whoami Wget xargs yes'
						;

		this.regexList = [	
            //Make sure the replacement for the callouts does not get highlighted
            {regex: /@@@@([0-9]?[0-9])@([0-9]?[0-9])@@@@/g, css: 'removed'},		
            {regex: /(\-(.)+?\s)|curl\s/ig, css: 'color2 bold'},
			{ regex: /^#!.*$/gm,											css: 'preprocessor bold' },
			{ regex: /\/[\w-\/]+/gm,										css: 'plain' },
			{ regex: SyntaxHighlighter.regexLib.singleLinePerlComments,		css: 'comments' },		// one line comments
			{ regex: SyntaxHighlighter.regexLib.doubleQuotedString,			css: 'string' },		// double quoted strings
			{ regex: SyntaxHighlighter.regexLib.singleQuotedString,			css: 'string' },		// single quoted strings
			{ regex: new RegExp(this.getKeywords(keywords), 'gm'),			css: 'keyword' },		// keywords
			{ regex: new RegExp(this.getKeywords(commands), 'gm'),			css: 'functions' }		// commands
			];
	}

	Brush.prototype	= new SyntaxHighlighter.Highlighter();
	Brush.aliases	= ['bash', 'shell', 'sh'];

	SyntaxHighlighter.brushes.Bash = Brush;

	// CommonJS
	typeof(exports) != 'undefined' ? exports.Brush = Brush : null;
})();

SyntaxHighlighter.brushes.Custom = function()
{
    var operators = '{ } [ ] : ,';
    
         
    this.regexList = [
        //Make sure the replacement for the callouts does not get highlighted
        {regex: /@@@@([0-9]?[0-9])@([0-9]?[0-9])@@@@/g, css: 'removed'},        
        //has a double quote followed by any sequence of characters followed by a double quote followed by colon 
        { regex: /.*\"(.*)\"(\s)*\:/g, css: 'keyword'},
        //opposite the above
        { regex: /[^(.*\".*\"(\s)*\:)]/g, css: 'comments'},

         //has a single quote followed by any sequence of characters followed by a single quote followed by colon 
        { regex: /.*\'.*\'(\s)*\:/g, css: 'keyword'},
        //opposite the above
        { regex: /[^(.*\'.*\'(\s)*\:)]/g, css: 'comments'},
        
        //Handle commas
        //a comma followed by 0 or 1 space
        { regex: /\,(\s)?/g, css: 'string'},  
        
        //Handle the special characters  
        //Any of the braces followed by 1 or 0 space  
        { regex: /(\{|\}|\[|\])(\s)?/g, css: 'plain'},
        //1 or 0 space followed by a } and followed by 1 or 0 space 
        { regex: /(\s)?\}(\s)?/g, css: 'plain'}   

    ];
};
 
SyntaxHighlighter.brushes.Custom.prototype = new SyntaxHighlighter.Highlighter();
SyntaxHighlighter.brushes.Custom.aliases  = ['json', 'JSON'];


;(function()
{
	// CommonJS
	SyntaxHighlighter = SyntaxHighlighter || (typeof require !== 'undefined'? require('shCore').SyntaxHighlighter : null);

	function Brush()
	{
		var keywords =	'break case catch continue ' +
						'default delete do else false  ' +
						'for function if in instanceof ' +
						'new null return super switch ' +
						'this throw true try typeof var while with'
						;

		var r = SyntaxHighlighter.regexLib;
		
		this.regexList = [
            //Make sure the replacement for the callouts does not get highlighted
            {regex: /@@@@([0-9]?[0-9])@([0-9]?[0-9])@@@@/g, css: 'removed'},    		
			{ regex: r.multiLineDoubleQuotedString,					css: 'string' },			// double quoted strings
			{ regex: r.multiLineSingleQuotedString,					css: 'string' },			// single quoted strings
			{ regex: r.singleLineCComments,							css: 'comments' },			// one line comments
			{ regex: r.multiLineCComments,							css: 'comments' },			// multiline comments
			{ regex: /\s*#.*/gm,									css: 'preprocessor' },		// preprocessor tags like #region and #endregion
			{ regex: new RegExp(this.getKeywords(keywords), 'gm'),	css: 'keyword' }			// keywords
			];
	
		this.forHtmlScript(r.scriptScriptTags);
	};

	Brush.prototype	= new SyntaxHighlighter.Highlighter();
	Brush.aliases	= ['js', 'jscript', 'javascript'];

	SyntaxHighlighter.brushes.JScript = Brush;

	// CommonJS
	typeof(exports) != 'undefined' ? exports.Brush = Brush : null;
})();


/**
 * SyntaxHighlighter
 * http://alexgorbatchev.com/SyntaxHighlighter
 *
 * SyntaxHighlighter is donationware. If you are using it, please donate.
 * http://alexgorbatchev.com/SyntaxHighlighter/donate.html
 *
 * @version
 * 3.0.83 (July 02 2010)
 * 
 * @copyright
 * Copyright (C) 2004-2010 Alex Gorbatchev.
 *
 * @license
 * Dual licensed under the MIT and GPL licenses.
 */
;(function()
{
	// CommonJS
	SyntaxHighlighter = SyntaxHighlighter || (typeof require !== 'undefined'? require('shCore').SyntaxHighlighter : null);

	function Brush()
	{
		function process(match, regexInfo)
		{
			var constructor = SyntaxHighlighter.Match,
				code = match[0],
				tag = new XRegExp('(&lt;|<)[\\s\\/\\?]*(?<name>[:\\w-\\.]+)', 'xg').exec(code),
				result = []
				;
		
			if (match.attributes != null) 
			{
				var attributes,
					regex = new XRegExp('(?<name> [\\w:\\-\\.]+)' +
										'\\s*=\\s*' +
										'(?<value> ".*?"|\'.*?\'|\\w+)',
										'xg');

				while ((attributes = regex.exec(code)) != null) 
				{
					result.push(new constructor(attributes.name, match.index + attributes.index, 'color1'));
					result.push(new constructor(attributes.value, match.index + attributes.index + attributes[0].indexOf(attributes.value), 'string'));
				}
			}

			if (tag != null)
				result.push(
					new constructor(tag.name, match.index + tag[0].indexOf(tag.name), 'keyword')
				);

			return result;
		}
	
		this.regexList = [
            //Make sure the replacement for the callouts does not get highlighted
            {regex: /@@@@([0-9]?[0-9])@([0-9]?[0-9])@@@@/g,css: 'removed'},		
            {regex: /\w+?\=/g, css: 'color1'},
            {regex: /\"[^\"]+\"/g, css: 'string'},		
			{ regex: new XRegExp('(\\&lt;|<)\\!\\[[\\w\\s]*?\\[(.|\\s)*?\\]\\](\\&gt;|>)', 'gm'),			css: 'color2' },	// <![ ... [ ... ]]>
			{ regex: SyntaxHighlighter.regexLib.xmlComments,												css: 'comments' },	// <!-- ... -->
			{ regex: new XRegExp('(&lt;|<)[\\s\\/\\?]*(\\w+)(?<attributes>.*?)[\\s\\/\\?]*(&gt;|>)', 'sg'), func: process }
		];
	};

	Brush.prototype	= new SyntaxHighlighter.Highlighter();
	Brush.aliases	= ['xml', 'xhtml', 'xslt', 'html'];

	SyntaxHighlighter.brushes.Xml = Brush;

	// CommonJS
	typeof(exports) != 'undefined' ? exports.Brush = Brush : null;
})();


;(function()
{
	// CommonJS
	SyntaxHighlighter = SyntaxHighlighter || (typeof require !== 'undefined'? require('shCore').SyntaxHighlighter : null);

	function Brush()
	{
		// Contributed by Gheorghe Milas and Ahmad Sherif
	
		var keywords =  'and assert break class continue def del elif else ' +
						'except exec finally for from global if import in is ' +
						'lambda not or pass print raise return try yield while';

		var funcs = '__import__ abs all any apply basestring bin bool buffer callable ' +
					'chr classmethod cmp coerce compile complex delattr dict dir ' +
					'divmod enumerate eval execfile file filter float format frozenset ' +
					'getattr globals hasattr hash help hex id input int intern ' +
					'isinstance issubclass iter len list locals long map max min next ' +
					'object oct open ord pow print property range raw_input reduce ' +
					'reload repr reversed round set setattr slice sorted staticmethod ' +
					'str sum super tuple type type unichr unicode vars xrange zip';

		var special =  'None True False self cls class_';

		this.regexList = [	
			    //Make sure the replacement for the callouts does not get highlighted
                {regex: /@@@@([0-9]?[0-9])@([0-9]?[0-9])@@@@/g, css: 'removed'},    
				{ regex: SyntaxHighlighter.regexLib.singleLinePerlComments, css: 'comments' },
				{ regex: /^\s*@\w+/gm, 										css: 'decorator' },
				{ regex: /(['\"]{3})([^\1])*?\1/gm, 						css: 'comments' },
				{ regex: /"(?!")(?:\.|\\\"|[^\""\n])*"/gm, 					css: 'string' },
				{ regex: /'(?!')(?:\.|(\\\')|[^\''\n])*'/gm, 				css: 'string' },
				{ regex: /\+|\-|\*|\/|\%|=|==/gm, 							css: 'keyword' },
				{ regex: /\b\d+\.?\w*/g, 									css: 'value' },
				{ regex: new RegExp(this.getKeywords(funcs), 'gmi'),		css: 'functions' },
				{ regex: new RegExp(this.getKeywords(keywords), 'gm'), 		css: 'keyword' },
				{ regex: new RegExp(this.getKeywords(special), 'gm'), 		css: 'color1' }
				];
			
		this.forHtmlScript(SyntaxHighlighter.regexLib.aspScriptTags);
	};

	Brush.prototype	= new SyntaxHighlighter.Highlighter();
	Brush.aliases	= ['py', 'python'];

	SyntaxHighlighter.brushes.Python = Brush;

	// CommonJS
	typeof(exports) != 'undefined' ? exports.Brush = Brush : null;
})();


;(function()
{
	// CommonJS
	SyntaxHighlighter = SyntaxHighlighter || (typeof require !== 'undefined'? require('shCore').SyntaxHighlighter : null);

	function Brush()
	{
		var keywords =	'abstract assert boolean break byte case catch char class const ' +
						'continue default do double else enum extends ' +
						'false final finally float for goto if implements import ' +
						'instanceof int interface long native new null ' +
						'package private protected public return ' +
						'short static strictfp super switch synchronized this throw throws true ' +
						'transient try void volatile while';

		this.regexList = [	
			//Make sure the replacement for the callouts does not get highlighted
            {regex: /@@@@([0-9]?[0-9])@([0-9]?[0-9])@@@@/g, css: 'removed'},    
			{ regex: SyntaxHighlighter.regexLib.singleLineCComments,	css: 'comments' },		// one line comments
			{ regex: /\/\*([^\*][\s\S]*)?\*\//gm,						css: 'comments' },	 	// multiline comments
			{ regex: /\/\*(?!\*\/)\*[\s\S]*?\*\//gm,					css: 'preprocessor' },	// documentation comments
			{ regex: SyntaxHighlighter.regexLib.doubleQuotedString,		css: 'string' },		// strings
			{ regex: SyntaxHighlighter.regexLib.singleQuotedString,		css: 'string' },		// strings
			{ regex: /\b([\d]+(\.[\d]+)?|0x[a-f0-9]+)\b/gi,				css: 'value' },			// numbers
			{ regex: /(?!\@interface\b)\@[\$\w]+\b/g,					css: 'color1' },		// annotation @anno
			{ regex: /\@interface\b/g,									css: 'color2' },		// @interface keyword
			{ regex: new RegExp(this.getKeywords(keywords), 'gm'),		css: 'keyword' }		// java keyword
			];

		this.forHtmlScript({
			left	: /(&lt;|<)%[@!=]?/g, 
			right	: /%(&gt;|>)/g 
		});
	};

	Brush.prototype	= new SyntaxHighlighter.Highlighter();
	Brush.aliases	= ['java'];

	SyntaxHighlighter.brushes.Java = Brush;

	// CommonJS
	typeof(exports) != 'undefined' ? exports.Brush = Brush : null;
})();

/**
 * SyntaxHighlighter
 * http://alexgorbatchev.com/SyntaxHighlighter
 *
 * SyntaxHighlighter is donationware. If you are using it, please donate.
 * http://alexgorbatchev.com/SyntaxHighlighter/donate.html
 *
 * @version
 * 3.0.83 (July 02 2010)
 * 
 * @copyright
 * Copyright (C) 2004-2010 Alex Gorbatchev.
 *
 * @license
 * Dual licensed under the MIT and GPL licenses.
 */
;(function()
{
	// CommonJS
	typeof(require) != 'undefined' ? SyntaxHighlighter = require('shCore').SyntaxHighlighter : null;

	function Brush()
	{
		// Contributed by Yegor Jbanov and David Bernard.
	
		var keywords =	'val sealed case def true trait implicit forSome import match object null finally super ' +
						'override try lazy for var catch throw type extends class while with new final yield abstract ' +
						'else do if return protected private this package false';

		var keyops =	'[_:=><%#@]+';

		this.regexList = [
			{ regex: SyntaxHighlighter.regexLib.singleLineCComments,			css: 'comments' },	// one line comments
			{ regex: SyntaxHighlighter.regexLib.multiLineCComments,				css: 'comments' },	// multiline comments
			{ regex: SyntaxHighlighter.regexLib.multiLineSingleQuotedString,	css: 'string' },	// multi-line strings
			{ regex: SyntaxHighlighter.regexLib.multiLineDoubleQuotedString,    css: 'string' },	// double-quoted string
			{ regex: SyntaxHighlighter.regexLib.singleQuotedString,				css: 'string' },	// strings
			{ regex: /0x[a-f0-9]+|\d+(\.\d+)?/gi,								css: 'value' },		// numbers
			{ regex: new RegExp(this.getKeywords(keywords), 'gm'),				css: 'keyword' },	// keywords
			{ regex: new RegExp(keyops, 'gm'),									css: 'keyword' }	// scala keyword
			];
	}

	Brush.prototype	= new SyntaxHighlighter.Highlighter();
	Brush.aliases	= ['scala'];

	SyntaxHighlighter.brushes.Scala = Brush;

	// CommonJS
	typeof(exports) != 'undefined' ? exports.Brush = Brush : null;
})();
