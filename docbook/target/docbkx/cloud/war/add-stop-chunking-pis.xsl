<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:db="http://docbook.org/ns/docbook"
    xmlns:raxm="http://docs.rackspace.com/api/metadata"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    exclude-result-prefixes="xs raxm db" version="2.0">

    <!--
        This xslt adds <?dbhtml stop-chunking?> processing instructions
        where appropriate for a given content type. This allows us to 
        configure the DocBook xslts to chunk deeply
     -->

    <xsl:template match="node() | @*">
        <xsl:copy>
            <xsl:apply-templates select="node() | @*"/>
        </xsl:copy>
    </xsl:template>

    <xsl:template match="*[./db:info/raxm:metadata]">
        <xsl:copy>
            <xsl:apply-templates select="@*"/>
            <xsl:choose>
                <xsl:when
                    test="
                            (./db:info/raxm:metadata//raxm:type = 'concept' and not(.//db:section/db:info/raxm:metadata)) (: Concepts that don't have descendant concepts stop chunking :)
                            ">
                    <xsl:processing-instruction name="dbhtml">stop-chunking</xsl:processing-instruction>
                </xsl:when>
                <xsl:otherwise/>
            </xsl:choose>
            <xsl:apply-templates select="node()"/>
        </xsl:copy>
    </xsl:template>
    

    <xsl:template match="db:section">
        <xsl:copy>
            <xsl:apply-templates select="@*"/>
            <xsl:choose>
                <xsl:when
                    test="
                    ancestor::*[./db:info/raxm:metadata//raxm:type = 'tutorial']                               (: Tutorials stop chunking after the first section. Tho there shouldn't be section/sections anyway :)
                    ">
                    <xsl:processing-instruction name="dbhtml">stop-chunking</xsl:processing-instruction>
                </xsl:when>
                <xsl:otherwise/>
            </xsl:choose>
            <xsl:apply-templates select="node()"/>
        </xsl:copy>
    </xsl:template>
    


</xsl:stylesheet>