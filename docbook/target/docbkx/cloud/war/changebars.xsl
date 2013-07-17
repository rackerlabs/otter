<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs"
    version="2.0">

        <!-- Check and see if you added this stuff to the stock xsls and remove this if you did -->
        <xsl:param name="show.changebars">1</xsl:param>
        <xsl:template match="text()[ ancestor::*/@revisionflag] | xref[ ancestor::*/@revisionflag]">
            <xsl:choose>
                <xsl:when test="$show.changebars != 0"><span class="{ancestor::*/@revisionflag[1]}"><xsl:apply-imports/></span></xsl:when>
                <xsl:otherwise><xsl:apply-imports/></xsl:otherwise>
            </xsl:choose>
        </xsl:template>
        <xsl:template match="*[substring(local-name(.),string-length(local-name(.)) - 4,5) = 'list' and ancestor-or-self::*/@revisionflag]|para[ancestor-or-self::*/@revisionflag]|figure[ancestor-or-self::*/@revisionflag]|informalfigure[ancestor-or-self::*/@revisionflag]|table[ancestor-or-self::*/@revisionflag]|informaltable[ancestor-or-self::*/@revisionflag]|procedure[ancestor-or-self::*/@revisionflag]">
            <xsl:choose>
                <xsl:when test="$show.changebars != 0"><div class="{ancestor-or-self::*/@revisionflag[1]}"><xsl:apply-imports/></div></xsl:when>
                <xsl:otherwise><xsl:apply-imports/></xsl:otherwise>
            </xsl:choose>
        </xsl:template>
        
    <!-- The following templates change the color of text flagged as reviewer, internal, or writeronly -->    
    <xsl:template match="text()[ contains(concat(';',ancestor::*/@security,';'),';internal;') ] | xref[ contains(concat(';',ancestor::*/@security,';'),';internal;') ]"><span class="internal"><xsl:apply-imports/></span></xsl:template>
    <xsl:template match="text()[ contains(concat(';',ancestor::*/@security,';'),';writeronly;') ] | xref[ contains(concat(';',ancestor::*/@security,';'),';writeronly;') ]"><span class="writeronly"><xsl:apply-imports/></span></xsl:template>
    <xsl:template match="text()[ contains(concat(';',ancestor::*/@security,';'),';reviewer;') ] | xref[ contains(concat(';',ancestor::*/@security,';'),';reviewer;') ]"><span class="remark"><xsl:apply-imports/></span></xsl:template>
    <xsl:template match="text()[ ancestor::*/@role = 'highlight' ] | xref[ ancestor::*/@role = 'highlight' ]" priority="10"><span class="remark"><xsl:apply-imports/></span></xsl:template>
    
</xsl:stylesheet>