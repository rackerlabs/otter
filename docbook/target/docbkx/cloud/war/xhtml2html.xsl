<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xhtml="http://www.w3.org/1999/xhtml"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs xhtml"
    version="2.0">
    <!--
    <xsl:output method="html" omit-xml-declaration="yes" indent="yes" doctype-system="about:legacy-compat"/>-->
    
    <xsl:strip-space elements="*"/>
    <xsl:preserve-space elements="xhtml:pre"/>
    
 <!--   <xsl:template match="/">
        <xsl:text disable-output-escaping='yes'>&lt;!DOCTYPE html></xsl:text>
        <xsl:apply-templates/>
    </xsl:template>-->
   
    <!-- attributes, commments, processing instructions, text: copy as is -->
    <xsl:template match="@*|comment()|processing-instruction()|text()">
        <xsl:copy-of select="."/>
    </xsl:template>
    
    <!-- elements: create a new element with the same name, but no namespace -->
    <xsl:template match="*">
        <xsl:element name="{local-name()}">
            <xsl:apply-templates select="@*|node()"/>
        </xsl:element>
    </xsl:template>
    
    
</xsl:stylesheet>