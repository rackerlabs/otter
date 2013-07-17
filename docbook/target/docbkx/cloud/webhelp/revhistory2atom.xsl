<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet 
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:exslt="http://exslt.org/common" 
    xmlns:date="http://exslt.org/dates-and-times" 
    xmlns:db="http://docbook.org/ns/docbook" 
    exclude-result-prefixes="date db exslt"
    xmlns="http://www.w3.org/2005/Atom" 
    version="1.1">
    
  <xsl:param name="canonical.url.base">
    <xsl:call-template name="pi-attribute">
      <xsl:with-param name="pis" select="/*/processing-instruction('rax')"/>
      <xsl:with-param name="attribute" select="'canonical.url.base'"/>
    </xsl:call-template>
  </xsl:param>
    
    <xsl:template name="revhistory2atom">
        <xsl:if test="exslt:node-set($profiled-nodes)//db:revhistory/db:revision and $canonical.url.base != ''">
          <xsl:call-template name="write.chunk">
            <xsl:with-param name="filename"><xsl:value-of select="concat($webhelp.base.dir,'/','atom-doctype.xml')"/></xsl:with-param>
            <xsl:with-param name="method" select="'xml'"/>
            <xsl:with-param name="encoding" select="'utf-8'"/>
            <xsl:with-param name="indent" select="'yes'"/>
            <xsl:with-param name="content">
                 <xsl:apply-templates select="exslt:node-set($profiled-nodes)//db:revhistory[1]"/>
            </xsl:with-param>
          </xsl:call-template>
        </xsl:if>
    </xsl:template>

    <xsl:template match="db:revhistory">
        <xsl:variable name="escapechars"> &amp;"'&lt;?</xsl:variable>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <title><xsl:value-of select="concat(exslt:node-set($profiled-nodes)/*/db:title[1],' ', exslt:node-set($profiled-nodes)/*/db:info/db:releaseinfo[1])"/> revision history</title>
            <link href="{substring-before($canonical.url.base,'/content')}/atom.xml" rel="self"/>
            <link href="{$canonical.url.base}/index.html"/>
            <id>
                <xsl:choose>
                    <xsl:when test="/*/@xml:id"><xsl:value-of select="/*/@xml:id"/></xsl:when>
                    <xsl:otherwise><xsl:value-of select="translate(exslt:node-set($profiled-nodes)//title[1],$escapechars,'_')"/></xsl:otherwise>
                </xsl:choose>
                </id>
            <updated>
                <xsl:call-template name="datetime.format">  
                    <xsl:with-param name="date" select="date:date-time()"/>  
                    <xsl:with-param name="format" select="'Y-m-d'"/>  
                </xsl:call-template>T<xsl:call-template name="datetime.format">  
                    <xsl:with-param name="date" select="date:date-time()"/>  
                    <xsl:with-param name="format" select="'X'"/>  
                </xsl:call-template>
            </updated>
            <xsl:apply-templates select="db:revision"/>
        </feed>
    </xsl:template>

    <xsl:template match="db:revision">
        <entry>
            <title>
                <xsl:choose>
                    <xsl:when test="db:revnumber"><xsl:value-of select="db:revnumber"/></xsl:when>
                    <xsl:otherwise><xsl:value-of select="db:date"/></xsl:otherwise>
                </xsl:choose>
            </title>
            <link type="text/html" href="{$canonical.url.base}/index.html"/>
            <id><xsl:value-of select="concat(/*/@xml:id,'-',db:date)"/></id>
            <updated><xsl:value-of select="db:date"/></updated>
            <content type="xhtml"><xsl:apply-templates select="db:revdescription|db:revremark"/></content>
        </entry>
    </xsl:template>

    <xsl:template match="db:revdescription">
        <xsl:variable name="xhtml">
            <xsl:apply-templates/>
        </xsl:variable>
        <div xmlns="http://www.w3.org/1999/xhtml">
            <xsl:apply-templates select="$xhtml" mode="fix-xrefs"/>
        </div>
    </xsl:template>
    
    <xsl:template match="html:a[@class = 'xref']" xmlns:html="http://www.w3.org/1999/xhtml" mode="fix-xrefs">
        <a xmlns="http://www.w3.org/1999/xhtml"> 
           <xsl:copy-of select="@*"/>
           <xsl:attribute name="href">
                <xsl:value-of select="concat('content/',@href)"/>
           </xsl:attribute>
            <xsl:apply-templates select="node()" mode="fix-xrefs"/>
        </a>
    </xsl:template>

    <xsl:template match="node() | @*" mode="fix-xrefs">
        <xsl:copy>
            <xsl:apply-templates select="node() | @*" mode="fix-xrefs"/>
        </xsl:copy>
    </xsl:template>
    
    
</xsl:stylesheet>