<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:db="http://docbook.org/ns/docbook"
		xmlns:f="http://docbook.org/xslt/ns/extension"
		xmlns:m="http://docbook.org/xslt/ns/mode"
		xmlns:n="http://docbook.org/xslt/ns/normalize"
		exclude-result-prefixes="db f m n"
		version="2.0">

  <xsl:import href="dist/xslt/base/common/preprocess.xsl"/>
  <xsl:import href="dist/xslt/base/common/functions.xsl"/>
  <xsl:import href="dist/xslt/base/common/l10n.xsl"/>
  <xsl:import href="dist/xslt/base/common/control.xsl"/>
  <xsl:import href="dist/xslt/base/html/param.xsl"/>

  <xsl:param name="preprocess" select="'profile'"/>
  <xsl:param name="body.fontset"/>
  <xsl:param name="stylesheet.result.type"/>
  <xsl:param name="VERSION"/>

  <xsl:param name="profile.audience" select="''"/>
  <xsl:param name="security">external</xsl:param>
  <xsl:param name="root.attr.status"><xsl:if test="/*[@status = 'draft']">draft;</xsl:if></xsl:param>
  <xsl:param name="profile.security">
    <xsl:choose>
      <xsl:when test="$security = 'external'"><xsl:value-of select="$root.attr.status"/>external</xsl:when>
      <xsl:when test="$security = 'internal'"><xsl:value-of select="$root.attr.status"/>internal</xsl:when>
      <xsl:when test="$security = 'reviewer'"><xsl:value-of select="$root.attr.status"/>reviewer;internal;external</xsl:when>
      <xsl:when test="$security = 'writeronly'"><xsl:value-of select="$root.attr.status"/>reviewer;internal;external;writeronly</xsl:when>
      <xsl:when test="$security = 'external'"><xsl:value-of select="$root.attr.status"/>external</xsl:when>
      <xsl:otherwise>
	<xsl:message terminate="yes"> 
	  ERROR: The value "<xsl:value-of select="$security"/>" is not valid for the security paramter. 
	         Valid values are: external, internal, reviewer, and writeronly. 
	</xsl:message>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="show.comments">
    <xsl:choose>
      <xsl:when test="$security = 'reviewer' or $security = 'writeronly'">1</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:param>


  <xsl:template match="/">
    <xsl:variable name="root" as="element()"
		  select="f:docbook-root-element(f:preprocess(/),$rootid)"/>
    <xsl:apply-templates select="$root" />
  </xsl:template>

  <xsl:template match="@*|node()" >
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

<!-- ================================================== -->
<!-- Overriding a couple of templates from 4-normalize.xsl to fix bugs. -->
  
<!-- Don't remove programlistings etc -->
  <xsl:template match="@*|node()" mode="m:verbatim-phase-1" xmlns:m="http://docbook.org/xslt/ns/mode">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()" mode="m:verbatim-phase-1"/>
    </xsl:copy>
  </xsl:template>

<!-- Move title into db:info if there's one outside  -->
  <xsl:template match="db:info" mode="m:normalize">
    <xsl:copy>
      <xsl:copy-of select="@*"/>
      <xsl:if test="not(db:title)">
        <xsl:copy-of select="preceding-sibling::db:title"/>
      </xsl:if>
      <xsl:call-template name="n:normalize-dbinfo"/>
    </xsl:copy>
  </xsl:template>

</xsl:stylesheet>