<xsl:stylesheet exclude-result-prefixes="d"              
        xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
        xmlns:d="http://docbook.org/ns/docbook"
	xmlns:exsl="http://exslt.org/common"
        xmlns:ng="http://docbook.org/docbook-ng" 
        xmlns:db="http://docbook.org/ns/docbook"
        xmlns:fb="http://ogp.me/ns/fb#"
        version="1.0" xmlns="http://www.w3.org/1999/xhtml">
  
  <xsl:import href="urn:docbkx:stylesheet-base/xhtml/chunk-common.xsl" />

    <xsl:template name="chunk-element-content">
        <xsl:param name="prev"/>
        <xsl:param name="next"/>
        <xsl:param name="nav.context"/>
        <xsl:param name="content">
            <xsl:apply-imports/>
        </xsl:param>

        <xsl:call-template name="user.preroot"/>

        <html>
            <xsl:call-template name="html.head">
                <xsl:with-param name="prev" select="$prev"/>
                <xsl:with-param name="next" select="$next"/>
            </xsl:call-template>

            <body>
                <xsl:call-template name="body.attributes"/>

                <xsl:call-template name="user.header.navigation">
                    <xsl:with-param name="prev" select="$prev"/>
                    <xsl:with-param name="next" select="$next"/>
                    <xsl:with-param name="nav.context" select="$nav.context"/>
                </xsl:call-template>


                <div id="content">

                    <xsl:call-template name="user.header.content"/>

                    <xsl:copy-of select="$content"/>

                    <xsl:call-template name="user.footer.content"/>

                    <xsl:call-template name="footer.navigation">
                        <xsl:with-param name="prev" select="$prev"/>
                        <xsl:with-param name="next" select="$next"/>
                        <xsl:with-param name="nav.context" select="$nav.context"/>
                    </xsl:call-template>
                </div>

                <xsl:call-template name="user.footer.navigation"/>
                <script type="text/javascript" src="{$webhelp.common.dir}jquery/jquery.qtip-1.0.0-rc3/jquery.qtip-1.0.0-rc3.min.js">
                   <xsl:comment>jQuery plugin for glossary popups. </xsl:comment>
                   $('a[title]').qtip({ style: { name: 'cream', tip: true } })
                </script>

            </body>
        </html>
        <xsl:value-of select="$chunk.append"/>
    </xsl:template>

</xsl:stylesheet>