  <xsl:stylesheet 
	xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
	xmlns="http://www.w3.org/1999/xhtml"
	version="1.1">

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

  </xsl:stylesheet>