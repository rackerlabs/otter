<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
		xmlns="http://www.w3.org/1999/xhtml"
		xmlns:xhtml="http://www.w3.org/1999/xhtml"
		xmlns:h="http://www.w3.org/1999/xhtml"
		xmlns:f="http://docbook.org/xslt/ns/extension"
		xmlns:t="http://docbook.org/xslt/ns/template"
		xmlns:m="http://docbook.org/xslt/ns/mode"
		xmlns:fn="http://www.w3.org/2005/xpath-functions"
		xmlns:ghost="http://docbook.org/ns/docbook/ephemeral"
		xmlns:db="http://docbook.org/ns/docbook"
		xmlns:tp="http://docbook.org/xslt/ns/template/private"
		xmlns:mp="http://docbook.org/xslt/ns/mode/private"
		xmlns:xdmp="http://marklogic.com/xdmp"
		xmlns:ext="http://docbook.org/extensions/xslt20"
		xmlns:xlink="http://www.w3.org/1999/xlink"
                xmlns:xs="http://www.w3.org/2001/XMLSchema"
                xmlns:raxm="http://docs.rackspace.com/api/metadata"
		exclude-result-prefixes="h f m fn db t ghost tp mp xs raxm xdmp ext xlink"
		version="2.0">

  <xsl:import href="dist/xslt/base/html/docbook.xsl"/>
  <!-- 
  <xsl:import href="static-header.xsl"/>
  -->
  <xsl:import href="changebars.xsl"/>
	
  <xsl:include href="dist/xslt/base/html/chunktemp.xsl"/>
  
  <xsl:param name="local.l10n.xml" select="document('')"/>
  <xsl:param name="profile.audience" select="''"/>
  
  <i18n xmlns="http://docbook.sourceforge.net/xmlns/l10n/1.0">
    <l:l10n 
      xmlns:l="http://docbook.sourceforge.net/xmlns/l10n/1.0"
      language="en" 
      english-language-name="English"> 
      <l:context name="xref">
        <l:template name="section" text="%t"/>
      </l:context>
    </l:l10n>
  </i18n>
  
  <xsl:param name="callout.unicode" select="1"/>
  <xsl:param name="callout.graphics" select="0"/>
  
  <xsl:param name="IndexWar">/</xsl:param>
  <xsl:param name="resource.root" select="concat($IndexWar,'/common/docbook/')"/>
  <xsl:param name="input.filename"/>
  <xsl:param name="use.id.as.filename" select="'1'"/>
  <!-- <xsl:param name="html.ext" select="'.jspx'"/> -->
  <xsl:param name="linenumbering" as="element()*">
  <!--  <ln xmlns="http://docbook.org/ns/docbook" path="literallayout" everyNth="2" width="3" separator=" " padchar=" " minlines="3"/>-->
    <!-- <ln xmlns="http://docbook.org/ns/docbook"  -->
    <!-- 	path="programlisting"  -->
    <!-- 	everyNth="2"  -->
    <!-- 	width="3"  -->
    <!-- 	separator=" "  -->
    <!-- 	padchar=" "  -->
    <!-- 	minlines="3"/> -->
    <!--<ln xmlns="http://docbook.org/ns/docbook" path="programlistingco" everyNth="2" width="3" separator=" " padchar=" " minlines="3"/>
    <ln xmlns="http://docbook.org/ns/docbook" path="screen" everyNth="2" width="3" separator=" " padchar=" " minlines="3"/>
    <ln xmlns="http://docbook.org/ns/docbook" path="synopsis" everyNth="2" width="3" separator=" " padchar=" " minlines="3"/>
    <ln xmlns="http://docbook.org/ns/docbook" path="address" everyNth="0"/>-->
    <ln xmlns="http://docbook.org/ns/docbook" path="epigraph/literallayout" everyNth="0"/>
  </xsl:param>

  <xsl:param name="toc.section.depth">1</xsl:param>
  <xsl:param name="chunk.section.depth">100</xsl:param>
		
  <xsl:param name="branding">rackspace</xsl:param>	
		
  <xsl:param name="enable.google.analytics">
    <xsl:choose>
      <xsl:when test="$branding = 'rackspace'">1</xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="google.analytics.id">
    <xsl:choose>
      <xsl:when test="$branding = 'rackspace'">UA-23102455-4</xsl:when>
      <xsl:otherwise/>
    </xsl:choose>
  </xsl:param>
  <xsl:param name="google.analytics.domain">
    <xsl:choose>
      <xsl:when test="$branding = 'rackspace'">.rackspace.com</xsl:when>
      <xsl:when test="$branding = 'openstack'">.openstack.org</xsl:when>
      <xsl:otherwise/>
    </xsl:choose>
  </xsl:param> 	
  
	<xsl:param name="enable.disqus">0</xsl:param>
	<xsl:param name="disqus.shortname">
		<xsl:choose>
			<xsl:when test="$branding = 'test'">jonathan-test-dns</xsl:when>
			<xsl:when test="$branding = 'rackspace'">rc-api-docs</xsl:when>
			<xsl:when test="$branding = 'openstack'">openstackdocs</xsl:when>
			<xsl:when test="$branding = 'openstackextension'">openstackdocs</xsl:when>
		</xsl:choose>
	</xsl:param>
	<xsl:param name="use.version.for.disqus">0</xsl:param>
	<xsl:variable name="version.for.disqus">
		<xsl:choose>
			<xsl:when test="$use.version.for.disqus!='0'">
				<xsl:value-of select="translate(/*/db:info/db:releaseinfo[1],' ','')"/>
			</xsl:when>
			<xsl:otherwise></xsl:otherwise>
		</xsl:choose>       
	</xsl:variable>	
	<xsl:param name="use.disqus.id">1</xsl:param>
	<xsl:param name="feedback.email" select="f:pi(processing-instruction('rax'),'feedback.email')"/>
	

  <xsl:param name="base.dir" select="'target/docbkx/xhtml/example/'"/>

  <xsl:param name="preprocess" select="'profile normalize'"/>
  <xsl:param name="project.build.directory">/home/dcramer/rax/published/cloud-servers-2x-upstream/target</xsl:param>
  <xsl:param name="glossary.collection" select="concat($project.build.directory,'/mvn/com.rackspace.cloud.api/glossary/glossary.xml')"/>  

  <xsl:param name="security">external</xsl:param>
  <xsl:param name="root.attr.status"><xsl:if test="/*[@status = 'draft']">draft;</xsl:if></xsl:param>
  <xsl:param name="profile.security">
    <xsl:choose>
      <xsl:when test="$security = 'external'"><xsl:value-of select="$root.attr.status"/>external</xsl:when>
      <xsl:when test="$security = 'internal'"><xsl:value-of select="$root.attr.status"/>internal;external</xsl:when>
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

  <xsl:param name="generate.toc" as="element()*">
    <tocparam xmlns="http://docbook.org/ns/docbook" path="appendix" toc="0" title="1"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="article/appendix" toc="0" title="1"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="article" toc="0" title="1"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="book" toc="0" title="1" figure="1" table="1" example="1" equation="1"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="chapter" toc="0" title="1"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="part" toc="0" title="1"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="preface" toc="0" title="1"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="qandadiv" toc="0"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="qandaset" toc="0"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="reference" toc="0" title="1"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="sect1" toc="0"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="sect2" toc="0"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="sect3" toc="0"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="sect4" toc="0"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="sect5" toc="0"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="section" toc="0"/>
    <tocparam xmlns="http://docbook.org/ns/docbook" path="set" toc="0" title="1"/>
  </xsl:param>
    
  <!-- TEMPORARY HACK!!! -->
  <xsl:template match="db:glossterm" name="db:glossterm">
    <xsl:param name="firstterm"/>
    <xsl:apply-templates/>  
  </xsl:template>

<xsl:template name="t:system-head-content">
  <xsl:param name="node" select="."/>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <!-- system.head.content is like user.head.content, except that
       it is called before head.content. This is important because it
       means, for example, that <style> elements output by system-head-content
       have a lower CSS precedence than the users stylesheet. -->

  <!-- See http://remysharp.com/2009/01/07/html5-enabling-script/ -->
  <!--
  <xsl:comment>[if lt IE 9]>
&lt;script src="http://html5shim.googlecode.com/svn/trunk/html5.js">&lt;/script>
&lt;![endif]</xsl:comment>
  -->
</xsl:template>

<xsl:template name="t:javascript">
  <xsl:param name="node" select="."/>
  
</xsl:template>

  <!--<xsl:param name="docbook.css" select="''"/>-->

<xsl:param name="autolabel.elements">
  <db:refsection/>
</xsl:param>

  <!-- We need too collect lists that contain their own raxm:metadata so we can 
       add <type>s to the bookinfo for resources mentioned in lists in the doc -->
  <xsl:param name="resource-lists" select="//db:itemizedlist[db:info/raxm:metadata]"/>
  
  <xsl:template match="node() | @*" mode="identity-copy">
    <xsl:copy>
      <xsl:apply-templates select="node() | @*" mode="identity-copy"/>
    </xsl:copy>
  </xsl:template>
  
  <xsl:template name="t:css"/>    
  
 
  <xsl:template match="/" priority="10">
    
    <xsl:choose>
      <xsl:when test="$rootid = ''">
        <xsl:apply-templates select="$chunks" mode="m:chunk"/>
      </xsl:when>
      <xsl:when test="$chunks[@xml:id = $rootid]">
        <xsl:apply-templates select="$chunks[@xml:id = $rootid]" mode="m:chunk"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:message terminate="yes">
          <xsl:text>There is no chunk with the ID: </xsl:text>
          <xsl:value-of select="$rootid"/>
        </xsl:message>
      </xsl:otherwise>
    </xsl:choose>
    
    <!-- We have to output xml to keep Calabash happy -->
    <xsl:apply-templates mode="identity-copy"/>
    
    <xsl:result-document 
        href="{$base.dir}/bookinfo.xml" 
        method="xml" indent="yes" encoding="UTF-8">
	<!--
    Here we write out the book info. It looks like this:		
    <products xmlns="">
        <product>
          <id>1</id>
          <types>
            <type>
              <id>1</id>
              <displayname>Legal notice</displayname>
              <url>/example/example-foo.html</url>
              <sequence>2</sequence> 
            </type>
            ...
          </types>     
        </product>
      </products>  
    	-->    
      
<!--      <xsl:variable name="productid">
      	<xsl:choose>
      		<xsl:when test="//db:productname"><xsl:apply-templates select="//db:productname" mode="bookinfo"/></xsl:when>
      		<xsl:otherwise>1</xsl:otherwise>
      	</xsl:choose>
      </xsl:variable>
-->            
      
      <products xmlns="">
        <xsl:choose>
          <xsl:when test="$rootid = ''">
            <xsl:for-each-group select="$chunks|$resource-lists" group-by="db:info/raxm:metadata//raxm:product">
              <product>
                <id><xsl:value-of select="f:productnumber(current-grouping-key())"/><!--                  <xsl:choose>
                    <xsl:when test="current-grouping-key() = 'servers'">1</xsl:when>
                    <xsl:when test="current-grouping-key() = 'cdb'">2</xsl:when>
                    <xsl:when test="current-grouping-key() = 'cm'">3</xsl:when>
                    <xsl:when test="current-grouping-key() = 'cbs'">4</xsl:when>
                    <xsl:when test="current-grouping-key() = 'files'">5</xsl:when>
                    <xsl:when test="current-grouping-key() = 'clb'">6</xsl:when>  
                    <xsl:when test="current-grouping-key() = 'auth'">7</xsl:when>  
                    <xsl:when test="current-grouping-key() = 'cdns'">8</xsl:when>                    
                    <xsl:otherwise>0</xsl:otherwise>
                  </xsl:choose>--></id>
                <types>
                  <xsl:variable name="types">
                    <xsl:apply-templates select="current-group()" mode="bookinfo">
                      <xsl:sort select="./db:info//raxm:type[1]"/>
                      <!-- Here we add <type>s to the bookinfo for resources mentioned in lists in the doc -->
                    </xsl:apply-templates>
                    <xsl:apply-templates 
                      select="$resource-lists[db:info/raxm:metadata//raxm:product = current-grouping-key()]/db:listitem" 
                      mode="bookinfo"/>
                  </xsl:variable>
                  <xsl:apply-templates select="$types/type" mode="copy-types">
                    <xsl:sort select="number(./id)" data-type="number"/>
                  </xsl:apply-templates>
                </types>
              </product>
            </xsl:for-each-group>
          </xsl:when>
          <xsl:when test="$chunks[@xml:id = $rootid]">
          <!--
              <xsl:for-each-group select="$chunks[@xml:id = $rootid]" group-by="db:info/raxm:product">
              <!-\- FIXME -\->
            </xsl:for-each-group>
          -->
          </xsl:when>
          <xsl:otherwise>
            <xsl:message terminate="yes">
              <xsl:text>There is no chunk with the ID: </xsl:text>
              <xsl:value-of select="$rootid"/>
            </xsl:message>
          </xsl:otherwise>
        </xsl:choose>
        
      <!--
      <product>
          <!-\- HACK...FIXME -\->
          <id><xsl:value-of select="$productid"/></id>
           <types>
      <xsl:choose>
        <xsl:when test="$rootid = ''">
          <xsl:apply-templates select="$chunks" mode="bookinfo"/>
        </xsl:when>
        <xsl:when test="$chunks[@xml:id = $rootid]">
          <xsl:apply-templates select="$chunks[@xml:id = $rootid]" mode="bookinfo"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:message terminate="yes">
            <xsl:text>There is no chunk with the ID: </xsl:text>
            <xsl:value-of select="$rootid"/>
          </xsl:message>
        </xsl:otherwise>
      </xsl:choose>
           </types>
        </product>
        -->
        
      </products>
    </xsl:result-document>
    
    <xsl:result-document 
      href="{$base.dir}/WEB-INF/web.xml" 
      method="xml" indent="yes" encoding="UTF-8">
      <web-app version="2.4" xmlns="http://java.sun.com/xml/ns/j2ee"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="
        http://java.sun.com/xml/ns/j2ee  http://java.sun.com/xml/ns/j2ee/web-app_2_4.xsd">
       <xsl:comment>Noop</xsl:comment>
      </web-app>
    </xsl:result-document>
    
  </xsl:template>
  
  <xsl:template match="node() | @*" mode="copy-types">
    <xsl:copy>
      <xsl:apply-templates select="node() | @*" mode="copy-types"/>
    </xsl:copy>
  </xsl:template>
  
  <xsl:template match="*" mode="bookinfo">
    <xsl:param name="type" select="normalize-space(db:info//raxm:type[1])"/>
    <xsl:param name="priority" select="normalize-space(db:info//raxm:priority[1])"/>
    
    <xsl:variable name="idNumber" select="f:calculatetype($type)"/>
<!--      <xsl:choose>
        <xsl:when test="$type = 'concept'">1</xsl:when>
        <xsl:when test="$type = 'apiref'">2</xsl:when>
        <xsl:when test="$type = 'resource'">3</xsl:when>
        <xsl:when test="$type = 'tutorial'">4</xsl:when>
        <xsl:when test="$type = 'apiref-mgmt'">5</xsl:when>
        <xsl:otherwise>100</xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
-->        
<!--    <xsl:variable name="priorityCalculated">
      <xsl:choose>
        <xsl:when test="normalize-space($priority) != ''">
          <xsl:value-of select="normalize-space($priority)"/>
        </xsl:when>
        <xsl:otherwise>100000</xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    -->
    <xsl:choose>
      <xsl:when test="self::db:itemizedlist"/>
      <xsl:when test="self::db:listitem">
        <type xmlns="">
          <id><xsl:value-of select="f:calculatetype(parent::*/db:info//raxm:type[1])"/></id>
          <displayname><xsl:value-of select=".//db:link[1]"/></displayname>
          <url><xsl:value-of select=".//db:link[1]/@xlink:href"/></url>
          <sequence><xsl:value-of select="f:calculatepriority(parent::*/db:info//raxm:priority[1])"/></sequence> 
        </type>        
      </xsl:when>
      <xsl:when test="self::db:chapter and ($type = 'apiref' or $type = 'apiref-mgmt')">
        <xsl:apply-templates select="db:section" mode="bookinfo-apiref">
          <xsl:with-param name="priorityCalculated" select="f:calculatepriority(normalize-space(db:info//raxm:priority[1]))"/>
          <xsl:with-param name="type" select="$idNumber"/>
        </xsl:apply-templates>
      </xsl:when>
      <xsl:otherwise>
        <type xmlns="">
          <id><xsl:value-of select="$idNumber"/></id>
          <displayname><xsl:value-of select="db:title|db:info/db:title"/></displayname>
          <url><xsl:value-of select="normalize-space(concat($IndexWar,'/',$input.filename, '/', f:href(/,.)))"/></url>
          <sequence><xsl:value-of select="f:calculatepriority(normalize-space(db:info//raxm:priority[1]))"/></sequence> 
        </type>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>
  
  <xsl:template match="db:section" mode="bookinfo-apiref">
    <xsl:param name="priorityCalculated"/>
    <xsl:param name="type"/>
    <type xmlns="">
      <id><xsl:value-of select="$type"/></id>
      <displayname><xsl:value-of select="db:title|db:info/db:title"/></displayname>
      <url><xsl:value-of select="normalize-space(concat($IndexWar,'/',$input.filename, '/', f:href(/,.)))"/></url>
      <sequence><xsl:value-of select="$priorityCalculated"/></sequence> 
    </type>
  </xsl:template>

  <!--<xsl:template match="db:productname" mode="bookinfo">
    <xsl:choose>
      <xsl:when test="preceding::db:productname"/>
      <xsl:when test="starts-with(normalize-space(.),'Cloud Servers')">1</xsl:when>
      <xsl:when test="starts-with(normalize-space(.),'Cloud Databases')">2</xsl:when>
      <xsl:when test="starts-with(normalize-space(.),'Cloud Monitoring')">3</xsl:when>
      <xsl:when test="starts-with(normalize-space(.),'Cloud Block Storage')">4</xsl:when>
      <xsl:when test="starts-with(normalize-space(.),'Cloud Files')">5</xsl:when>
      <xsl:otherwise>1</xsl:otherwise>
    </xsl:choose>  
  </xsl:template>
  -->
  <xsl:template match="text()" mode="bookinfo"/>

  <xsl:template match="*" mode="m:chunk" priority="10">
    <xsl:variable name="chunkfn" select="f:chunk-filename(.)"/>
    
    <xsl:variable name="pinav"
      select="(f:pi(./processing-instruction('dbhtml'), 'navigation'),'true')[1]"/>
    
    <xsl:variable name="chunk" select="key('id', generate-id(.), $chunk-tree)"/>
    <xsl:variable name="nchunk" select="($chunk/following::h:chunk|$chunk/descendant::h:chunk)[1]"/>
    <xsl:variable name="pchunk" select="($chunk/preceding::h:chunk|$chunk/parent::h:chunk)[last()]"/>
    <xsl:variable name="uchunk" select="$chunk/ancestor::h:chunk[1]"/>
    <xsl:variable name="prodname" select="f:productname(string((ancestor-or-self::*/db:info//raxm:product)[1])[1])" />

    <!--
    <xsl:message>Creating chunk: <xsl:value-of select="concat($base.dir,$chunkfn)"/></xsl:message>
    -->
    
    <xsl:result-document href="{$base.dir}{$chunkfn}" method="xhtml" indent="no">
      <html>
        <xsl:call-template name="t:head">
          <xsl:with-param name="node" select="."/>
         <xsl:with-param name="prodname" select="$prodname"/>
        </xsl:call-template>
        <body  class="hybrid-home">

	  <!-- START HEADER -->
	  <div id="raxdocs-header">
	    <xsl:comment/>
	  </div>
	  <!-- END HEADER -->


			<div id="content-home-wrap">
				<div class="container_12">
					<table class="content-home-table">
					  <tbody>
					    <tr>
					<td id="sidebar">
						<div id="treeDiv">
							<div id="ulTreeDiv">
								<ul id="tree" class="filetree">
									<xsl:apply-templates select="ancestor-or-self::db:chapter" mode="mp:toc">
                        <xsl:with-param name="toc-context" select="."/>
									</xsl:apply-templates>									  
								</ul>
							</div>
						</div>
					</td>
					      
					<!-- END TOC -->

					<td id="main-content">
						
						<div class="page">
							<xsl:call-template name="t:body-attributes"/>
							<xsl:if test="@status">
								<xsl:attribute name="class" select="@status"/>
							</xsl:if>
							
							<div class="content">
								<xsl:if test="$pinav = 'true'">
									<xsl:call-template name="t:user-header-content">
										<xsl:with-param name="node" select="."/>
										<xsl:with-param name="next" select="key('genid', $nchunk/@xml:id)"/>
										<xsl:with-param name="prev" select="key('genid', $pchunk/@xml:id)"/>
										<xsl:with-param name="up" select="key('genid', $uchunk/@xml:id)"/>
									</xsl:call-template>
								</xsl:if>
								
								<div class="body">
								  <!-- Title and breadcrumbs: WIP -->
								  <!--  
								  <h1><xsl:value-of select="f:productname(string(ancestor-or-self::*/db:info//raxm:product[1])[1])"/></h1>
								  -->
								  <h1><xsl:value-of select="$prodname"/></h1>
<!--                    <xsl:choose>
                      <xsl:when test="(ancestor-or-self::*/db:info//raxm:product[1])[1] = 'servers'">
                        <h1>Cloud Servers</h1>
                      </xsl:when>
                      <xsl:when test="(ancestor-or-self::*/db:info//raxm:product[1])[1] = 'files'">
                        <h1>Cloud Files</h1>
                      </xsl:when>
                      <xsl:when test="(ancestor-or-self::*/db:info//raxm:product[1])[1] = 'clb'">
                        <h1>Cloud Loadbalancers</h1>
                      </xsl:when>
                      <xsl:when test="(ancestor-or-self::*/db:info//raxm:product[1])[1] = 'cm'">
                        <h1>Cloud Montioring</h1>
                      </xsl:when>
                      <xsl:when test="(ancestor-or-self::*/db:info//raxm:product[1])[1] = 'cdb'">
                        <h1>Cloud Databases</h1>
                      </xsl:when>
                      <xsl:when test="(ancestor-or-self::*/db:info//raxm:product[1])[1] = 'cbs'">
                        <h1>Cloud Block Storage</h1>
                      </xsl:when>
                      <xsl:otherwise/>
                    </xsl:choose>
--> 								  <div id="breadcrumbs">
								    <xsl:choose>
								      <xsl:when test="(ancestor-or-self::*/db:info//raxm:type[1])[1] = 'tutorial'">
								        <a href="#">Tutorials</a><xsl:text> &gt; </xsl:text><a href="{$IndexWar}/index.jsp" onclick="_gaq.push(['_trackEvent', 'Breadcrumbs', 'landing.jsp', 'click', 1]);"><xsl:value-of select="f:productname(string(ancestor-or-self::*/db:info//raxm:product[1])[1])"/></a> <xsl:if test="parent::db:chapter"><xsl:text> &gt; </xsl:text><a href="{f:href(/,key('genid', $uchunk/@xml:id))}" onclick="_gaq.push(['_trackEvent', 'Breadcrumbs', '{f:href(/,key('genid', $uchunk/@xml:id))}', 'click', 1]);"><xsl:apply-templates select="key('genid', $uchunk/@xml:id)" mode="m:object-title-markup"/></a></xsl:if>
								      </xsl:when>								     
								      <xsl:when test="(ancestor-or-self::*/db:info//raxm:type[1])[1] = 'concept'">
								        <a href="#">Concepts</a><xsl:text> &gt; </xsl:text><a href="{$IndexWar}/index.jsp" onclick="_gaq.push(['_trackEvent', 'Breadcrumbs', 'landing.jsp', 'click', 1]);"><xsl:value-of select="f:productname(string((ancestor-or-self::*/db:info//raxm:product)[1])[1])"/></a> <xsl:if test="parent::db:chapter"><xsl:text> &gt; </xsl:text><a href="{f:href(/,key('genid', $uchunk/@xml:id))}" onclick="_gaq.push(['_trackEvent', 'Breadcrumbs', '{f:href(/,key('genid', $uchunk/@xml:id))}', 'click', 1]);"><xsl:apply-templates select="key('genid', $uchunk/@xml:id)" mode="m:object-title-markup"/></a></xsl:if>
								      </xsl:when>
								      <xsl:when test="(ancestor-or-self::*/db:info//raxm:type[1])[1] = 'apiref'">
								        <a href="#">API Documentation</a><xsl:text> &gt; </xsl:text><a href="{$IndexWar}/index.jsp" onclick="_gaq.push(['_trackEvent', 'Breadcrumbs', 'landing.jsp', 'click', 1]);"><xsl:value-of select="f:productname(string((ancestor-or-self::*/db:info//raxm:product)[1])[1])"/></a> <xsl:if test="parent::db:chapter"><xsl:text> &gt; </xsl:text><a href="{f:href(/,key('genid', $uchunk/@xml:id))}" onclick="_gaq.push(['_trackEvent', 'Breadcrumbs', '{f:href(/,key('genid', $uchunk/@xml:id))}', 'click', 1]);"><xsl:apply-templates select="key('genid', $uchunk/@xml:id)" mode="m:object-title-markup"/></a></xsl:if>
								      </xsl:when>
								      <xsl:otherwise>
								        
								      </xsl:otherwise>
								    </xsl:choose>
								    &#160;
								  </div>
								  <hr/>
								  <xsl:choose>
								    <xsl:when test="key('genid', $uchunk/@xml:id)/db:info//raxm:type[normalize-space(.) = 'tutorial']">
								  <h3>Tutorial: <xsl:apply-templates select="key('genid', $uchunk/@xml:id)" mode="m:object-title-markup"/></h3>
								  <xsl:apply-templates select="key('genid', $uchunk/@xml:id)" mode="beadbar">
								    <xsl:with-param name="current-node" select="generate-id(.)"/>
								  </xsl:apply-templates>
								      <br/>
								    </xsl:when>
								  </xsl:choose>
								  
									<xsl:apply-templates select=".">
										<xsl:with-param name="override-chunk" select="true()"/>
									</xsl:apply-templates>
								</div>
							</div>
							
							<xsl:if test="$pinav = 'true'">
								<xsl:call-template name="t:user-footer-content">
									<xsl:with-param name="node" select="."/>
									<xsl:with-param name="next" select="key('genid', $nchunk/@xml:id)"/>
									<xsl:with-param name="prev" select="key('genid', $pchunk/@xml:id)"/>
									<xsl:with-param name="up" select="key('genid', $uchunk/@xml:id)"/>
								</xsl:call-template>
							</xsl:if>
						</div>
					</td>
					    </tr>
					  </tbody>
					</table>
				</div>
			</div>
        	
       
          <!-- BEGIN FOOTER -->
           
	  <div id="rax-footer">
	    <!-- <xsl:call-template name="static-footer"/> -->
	  -->
	  </div>
	  
	  <!-- END FOOTER -->
        </body>
      </html>
    </xsl:result-document>
  </xsl:template>
  
  
  <xsl:template name="anchor">
    <xsl:param name="node" select="."/>
    <xsl:param name="force" select="0"/>
    
    <xsl:if test="$force != 0 or ($node/@id or $node/@xml:id)">
      <a name="{f:node-id($node)}" id="{f:node-id($node)}">&#160;</a>
    </xsl:if>
  </xsl:template>
  

<xsl:template name="t:user-head-content">
  <xsl:param name="node" select="."/>
  
  <script type="text/javascript" src="{$IndexWar}/common/scripts/jquery-1.4.3.min.js"><xsl:comment/></script>
  <script type="text/javascript" src="{$IndexWar}/common/scripts/jquery-hoverintent.js"><xsl:comment/></script>
  <script type="text/javascript" src="{$IndexWar}/common/scripts/rackspacemin-1332945039.js"><xsl:comment/></script>
  
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/docbook/css/default.css"/>
  <link rel="shortcut icon" href="{$IndexWar}/common/images/favicon-{$branding}.ico" type="image/x-icon"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/rackspace-min1333990221.css"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/custom.css"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/jquery-ui-1.8.2.custom.css"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/jquery.treeview.css"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/jquery.qtip.css"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/managed-rackspace.css"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/positioning-rackspace.css"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/newformat.css"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/style-new.css"/>
  <link rel="stylesheet" type="text/css" href="{$IndexWar}/common/css/rackspace-header1.css"/>
  <link type="text/css" rel="stylesheet" href="{$IndexWar}/common/css/rax-overrides.css"/>
  <link type="text/css" rel="stylesheet" href="{$IndexWar}/common/syntaxhighlighter/styles/shCoreDefault.css"/>

  
  
  <xsl:if test="//db:annotation">
    <script type="text/javascript" src="{concat($resource.root, 'js/AnchorPosition.js')}"><xsl:comment/></script>
    <script type="text/javascript" src="{concat($resource.root, 'js/PopupWindow.js')}"><xsl:comment/></script>
    <script type="text/javascript" src="{concat($resource.root, 'js/annotation.js')}"><xsl:comment/></script>
  </xsl:if>
  <script type="text/javascript" src="{concat($resource.root, 'js/dbmodnizr.js')}"><xsl:comment/></script>
  <script type="text/javascript" src="{$IndexWar}/common/scripts/newformat.js"><xsl:comment/></script> 
  <script type="text/javascript" src="{$IndexWar}/common/scripts/docs.js"><xsl:comment/></script>
  <script type="text/javascript" src="{$IndexWar}/common/scripts/rackspace-header2.js"><xsl:comment/></script>
  <script type="text/javascript" src="{$IndexWar}/common/scripts/smartbutton.js"><xsl:comment/></script>
  <script type="text/javascript" src="{$IndexWar}/common/scripts/munchkin.js"><xsl:comment/></script>
  <script type="text/javascript" src="{concat($IndexWar,'/common/syntaxhighlighter/scripts/shCore.js')}"><xsl:comment/></script>
  <script type="text/javascript" src="{concat($IndexWar,'/common/syntaxhighlighter/scripts/shSelect.js')}"><xsl:comment/></script>
  
  <script>
   $(function(){
	  $.getJSON("/new/IndexServlet?headerfooter=1",{"headerfooter" : "1"},function(data){
		  getHeader(data);
	   });
    });
  </script>
  <script>
    $(function(){
	   $.getJSON("/new/IndexServlet?headerfooter=3",{"headerfooter" : "3"},function(data){
		 getFooter(data,"3");
	   });
    });
  </script>
  
  <xsl:if test="$enable.google.analytics = '1' and not($google.analytics.id = '')">
    <script type="text/javascript">
	    var _gaq = _gaq || [];
	    _gaq.push(['_setAccount', '<xsl:value-of select="$google.analytics.id"/>']);
	    <xsl:choose>
	        <xsl:when test="$google.analytics.domain = ''"><!-- Do nothing --></xsl:when>
	        <xsl:otherwise>
	    _gaq.push(['_setDomainName', '<xsl:value-of select="$google.analytics.domain"/>']);	        
	        </xsl:otherwise>	
	    </xsl:choose>    
	  </script>
    <script type="text/javascript" src="{$IndexWar}/common/scripts/ga.js">
	    <xsl:comment></xsl:comment>
	  </script>
  </xsl:if>
  
  <xsl:if test="$node//db:programlisting[@language] or $node//db:screen[@language] or $node//db:literallayout[@language]">
    <script type="text/javascript">
               SyntaxHighlighter.config.space = '&#32;';
               SyntaxHighlighter.all();
    </script>      
  </xsl:if>
  
</xsl:template>

	<!-- Overriding this so I can add the preferred classes and ids -->
	<xsl:template name="tp:make-toc">
		<xsl:param name="toc-context" select="."/>
		<xsl:param name="toc.title" select="true()"/>
		<xsl:param name="nodes" select="()"/>
		
		<xsl:variable name="toc.title">
			<xsl:if test="$toc.title">
				<p>
					<b>
						<xsl:call-template name="gentext">
							<xsl:with-param name="key">TableofContents</xsl:with-param>
						</xsl:call-template>
					</b>
				</p>
			</xsl:if>
		</xsl:variable>
		
		<xsl:choose>
			<xsl:when test="$manual.toc != ''">
				<xsl:variable name="id" select="f:node-id(.)"/>
				<xsl:variable name="toc" select="document($manual.toc, .)"/>
				<xsl:variable name="tocentry" select="$toc//db:tocentry[@linkend=$id]"/>
				<xsl:if test="$tocentry and $tocentry/*">
					<div class="ulTreeDiv">
						<xsl:copy-of select="$toc.title"/>
						<ul id="tree" class="filetree">
							<xsl:call-template name="t:manual-toc">
								<xsl:with-param name="tocentry" select="$tocentry/*[1]"/>
							</xsl:call-template>
						</ul>
					</div>
				</xsl:if>
			</xsl:when>
			<xsl:otherwise>
				<xsl:if test="$nodes">
					<div class="ulTreeDiv">
						<xsl:copy-of select="$toc.title"/>
						<ul id="tree" class="filetree">
							<xsl:apply-templates select="$nodes" mode="mp:toc">
								<xsl:with-param name="toc-context" select="$toc-context"/>
							</xsl:apply-templates>
						</ul>
					</div>
				</xsl:if>
			</xsl:otherwise>
		</xsl:choose>
	</xsl:template>
	
	<xsl:template name="t:user-footer-content">
		<xsl:param name="node" select="."/>
		<xsl:param name="next" select="()"/>
		<xsl:param name="prev" select="()"/>
		<xsl:param name="up" select="()"/>
	

<xsl:choose>
  <xsl:when test="./db:info//raxm:type[normalize-space(.) = 'tutorial']">
    <div class="starttutorial">
      <img src="{$IndexWar}/common/images/BigTutorialArrow.png" class="bigtutorialarrow"/>    
      <div id="starttutoriallink">
        <a href="{f:href(/,$next[1])}" onclick="_gaq.push(['_trackEvent', 'Tutorial', 'Next', 'click', 1]);">Start!</a>
      </div>
    </div>
    <br/>
    <br/>    
  </xsl:when>
  <xsl:when test="$up/db:info//raxm:type[normalize-space(.) = 'tutorial']">
	  <img src="{$IndexWar}/common/images/BigTutorialArrow.png" class="bigtutorialarrow"/>
	  <div class="bigtypeprogress">Success!</div>
		<br/>
	  <br/>

		<div id="prevnextbuttons">
			<xsl:if test="$prev">
			<div id = "previouslink">
				<span id="previousbutton">
					<a>
						<xsl:attribute name="href">
							<xsl:choose>
								<xsl:when test="$prev and not($prev = $node)">
									<xsl:value-of select="f:href(/,$prev[1])"/>
								</xsl:when>
								<xsl:otherwise>#</xsl:otherwise>
							</xsl:choose>	
						</xsl:attribute>
						&lt;&#160;Previous
					</a>
				</span>
				<span id="previouschunk">
					<xsl:apply-templates select="$prev" mode="m:object-title-markup"/>
				</span>
			</div>
			</xsl:if>
			<xsl:if test="$next">
				<div id="nextlink">
				<span id="nextbutton">
					<a>
						<xsl:attribute name="href">
							<xsl:choose>
								<xsl:when test="$next and not($next = $node)">
								<xsl:value-of select="f:href(/,$next[1])"/>
								</xsl:when>
								<xsl:otherwise>#</xsl:otherwise>
							</xsl:choose>							
						</xsl:attribute>
						Next&#160;&gt;
					</a>
				</span>
				<span id="nextchunk">
					<xsl:apply-templates select="$next" mode="m:object-title-markup"/>
				</span>
			</div>
			</xsl:if>
		</div>
  </xsl:when>
</xsl:choose>
	  
		<xsl:if test="$enable.disqus!='0' and (//db:section[not(@xml:id)] or //db:chapter[not(@xml:id)] or //db:part[not(@xml:id)] or //db:appendix[not(@xml:id)] or //db:preface[not(@xml:id)] or /*[not(@xml:id)])">
			<xsl:message terminate="yes"> 
				<xsl:for-each select="//db:section[not(@xml:id)]|//db:chapter[not(@xml:id)]|//db:part[not(@xml:id)]|//db:appendix[not(@xml:id)]|//db:preface[not(@xml:id)]|/*[not(@xml:id)]">
					ERROR: The <xsl:value-of select="local-name()"/> "<xsl:value-of select=".//db:title[1]"/>" is missing an id.
				</xsl:for-each>
				When Disqus comments are enabled, the root element and every part, chapter, appendix, preface, and section must have an xml:id attribute.
			</xsl:message>
		</xsl:if>
		
		<!-- Alternate location for SyntaxHighlighter scripts -->
		
		
<!--		<script type="text/javascript" src="../common/main.js">
            <xsl:comment></xsl:comment>
        </script>-->
		
		<xsl:if test="$enable.disqus != '0'">
			<hr />
			<xsl:choose>
				<xsl:when test="$enable.disqus = 'intranet'">
					<xsl:if test="$feedback.email =''">
						<xsl:message terminate="yes">
							ERROR: Feedback email not set but internal comments are enabled.
						</xsl:message>
					</xsl:if>
					<script language="JavaScript" src="/comments.php?email={$feedback.email}" type="text/javascript"><xsl:comment/></script>
					<noscript>You must have JavaScript enabled to view and post comments.</noscript>
				</xsl:when>
				<xsl:otherwise>
					
					<div id="disqus_thread">
						<script type="text/javascript">
	      var disqus_shortname = '<xsl:value-of select="$disqus.shortname"/>';
	      <xsl:if test="$use.disqus.id != '0'">
	      var disqus_identifier = '<xsl:value-of select="/*/@xml:id"/><xsl:value-of select="$version.for.disqus"/><xsl:value-of select="@xml:id"/>';
	      </xsl:if>
	    </script>
						<noscript>Please enable JavaScript to view the <a href="http://disqus.com/?ref_noscript">comments powered by Disqus.</a></noscript>
						<script type="text/javascript" src="{$IndexWar}/common/scripts/comments.js"><xsl:comment/></script>
					</div>	  
				</xsl:otherwise>
			</xsl:choose>
		</xsl:if>
		
		
		
	</xsl:template>

	<!-- ======================================== -->
	<!-- Customized from html/autotoc.xsl         -->
	<!-- Adding id="currentchapter" to <li> so we -->
	<!-- can style it.                            -->
	<!-- ======================================== -->
<xsl:template name="tp:subtoc">
  <xsl:param name="toc-context" select="."/>
  <xsl:param name="nodes" select="()"/>

  <xsl:variable name="subtoc" as="element()">
    <ul class="toc">
      <xsl:apply-templates mode="mp:toc" select="$nodes">
        <xsl:with-param name="toc-context" select="$toc-context"/>
      </xsl:apply-templates>
    </ul>
  </xsl:variable>

  <xsl:variable name="depth" as="xs:integer">
    <xsl:choose>
      <xsl:when test="self::db:section">
        <xsl:value-of select="count(ancestor::db:section) + 1"/>
      </xsl:when>
      <xsl:when test="self::db:sect1">1</xsl:when>
      <xsl:when test="self::db:sect2">2</xsl:when>
      <xsl:when test="self::db:sect3">3</xsl:when>
      <xsl:when test="self::db:sect4">4</xsl:when>
      <xsl:when test="self::db:sect5">5</xsl:when>
      <xsl:when test="self::db:refsect1">1</xsl:when>
      <xsl:when test="self::db:refsect2">2</xsl:when>
      <xsl:when test="self::db:refsect3">3</xsl:when>
      <xsl:when test="self::db:simplesect">
	<!-- sigh... -->
	<xsl:choose>
	  <xsl:when test="parent::db:section">
            <xsl:value-of select="count(ancestor::db:section)"/>
          </xsl:when>
          <xsl:when test="parent::db:sect1">2</xsl:when>
          <xsl:when test="parent::db:sect2">3</xsl:when>
          <xsl:when test="parent::db:sect3">4</xsl:when>
          <xsl:when test="parent::db:sect4">5</xsl:when>
          <xsl:when test="parent::db:sect5">6</xsl:when>
          <xsl:when test="parent::db:refsect1">2</xsl:when>
          <xsl:when test="parent::db:refsect2">3</xsl:when>
          <xsl:when test="parent::db:refsect3">4</xsl:when>
          <xsl:otherwise>1</xsl:otherwise>
        </xsl:choose>
      </xsl:when>
      <xsl:otherwise>0</xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="depth.from.context"
		select="count(ancestor::*)-count($toc-context/ancestor::*)"/>

  <xsl:variable name="subtoc.list" select="$subtoc"/>
  <xsl:variable name="child-sections">
    <xsl:apply-templates select="./db:section" mode="child-sections">
      <xsl:with-param name="toc-context" select="$toc-context"/>
    </xsl:apply-templates>
  </xsl:variable>
  
  <xsl:variable name="show.subtoc" as="xs:boolean"
		select="(count($subtoc/*) &gt; 0
			and $toc.section.depth > $depth and exists($nodes)
			and $toc.max.depth > $depth.from.context)
			or 
			(: Here we show the child section's toc if we are the parent of the current section or if we're the current section :)
			(($child-sections/* or f:href(/,.) = f:href(/,$toc-context)) and exists($nodes) and count($subtoc/*) &gt; 0)"/>

  <li>
    <xsl:if test="f:href(/,.) = f:href(/,$toc-context)">
      <xsl:attribute name="id">currentchapter</xsl:attribute>
    </xsl:if>

    <xsl:call-template name="tp:toc-line">
      <xsl:with-param name="toc-context" select="$toc-context"/>
      <!-- Pass this in to make link to apiref wrapper dead -->
<!--      <xsl:with-param name="omit.link" as="xs:boolean">
        <xsl:choose>
          <xsl:when test="self::db:section and starts-with(ancestor::*/db:info/raxm:metadata//raxm:type, 'apiref-')">
            <xsl:value-of select="boolean('true')"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:value-of select="boolean('false')"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:with-param>-->
    </xsl:call-template>
    <xsl:if test="$show.subtoc">
      <xsl:copy-of select="$subtoc.list"/>
    </xsl:if>
  </li>
</xsl:template>
  
  <xsl:template name="tp:toc-line">
    <xsl:param name="toc-context" select="."/>
    <xsl:param name="depth" select="1"/>
    <xsl:param name="depth.from.context" select="8"/>
    <xsl:param name="omit.link" select="false()" as="xs:boolean"/>
    <span>
      <a href="{f:href(/,.)}" onclick="_gaq.push(['_trackEvent', 'SidebarToc', '{f:href(/,.)}', 'click', 1]);">
<!--        <xsl:attribute name="href">
          <xsl:choose>
            <xsl:when test="$omit.link">#</xsl:when>
            <xsl:otherwise><xsl:value-of select="f:href(/,.)"/></xsl:otherwise>
          </xsl:choose>
        </xsl:attribute>-->
        <xsl:variable name="label">
          <xsl:apply-templates select="." mode="m:label-content"/>
        </xsl:variable>
        <xsl:copy-of select="$label"/>
        <xsl:if test="$label != ''">
          <xsl:value-of select="$autotoc.label.separator"/>
        </xsl:if>
        
        <xsl:apply-templates select="." mode="m:titleabbrev-content"/>
      </a>
    </span>
  </xsl:template>
  
  <!-- We use this template to figure out if we're the parent of the current section -->
  <xsl:template match="db:section" mode="child-sections">
    <xsl:param name="toc-context"/>
    <xsl:if test="f:href(/,.) = f:href(/,$toc-context)"><true/></xsl:if>
  </xsl:template>
	<!-- ======================================== -->
	<!-- End of autotoc.xsl customization         -->
	<!-- ======================================== -->

  <xsl:template match="*" mode="beadbar">
    <xsl:param name="current-node"/>
    <div class="progressindicator">
      <xsl:apply-templates select="db:section" mode="beadbar-steps">
        <xsl:with-param name="current-node" select="$current-node"/>
      </xsl:apply-templates>
    </div>
  </xsl:template>

  <xsl:template match="db:section" mode="beadbar-steps">
    <xsl:param name="current-node"/>

    <xsl:variable name="gray">
      <xsl:choose>
        <xsl:when test="following-sibling::db:section[generate-id(.) = $current-node] or generate-id(.) = $current-node"/>
        <xsl:otherwise>gray</xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:choose>
    <xsl:when test="position() &lt; 10">
    <div>
      <xsl:attribute name="id">
        <xsl:value-of select="concat('step',position() - 1)"/>
      </xsl:attribute>
     <xsl:choose>
       <xsl:when test="position() = 1">
         <a href="{f:href(/,.)}" onclick="_gaq.push(['_trackEvent', 'Tutorial', 'Bead: {f:href(/,.)}', 'click', 1]);">
          <span class="firstbead"><img src="{$IndexWar}/common/images/bead.png"/></span>
          <span class="firststeptext  currentstep">
             <xsl:attribute name="class">
               <xsl:choose>
                 <xsl:when test="$current-node = generate-id(.)">firststeptext currentstep</xsl:when>
                 <xsl:otherwise>firststeptext</xsl:otherwise>
              </xsl:choose>
            </xsl:attribute>
            <xsl:apply-templates select="." mode="m:object-title-markup"/></span>
           </a>
       </xsl:when>
       <xsl:otherwise>
         <span class="stepline"><img class="stepline" src="{$IndexWar}/common/images/line{$gray}.png"/></span>
         <span class="stepbead"><a href="{f:href(/,.)}" onclick="_gaq.push(['_trackEvent', 'Tutorial', 'Bead: {f:href(/,.)}', 'click', 1]);"><img src="{$IndexWar}/common/images/bead{$gray}.png"/></a></span>
         <span class="steptext">
           <xsl:attribute name="class">
             <xsl:choose>
               <xsl:when test="$current-node = generate-id(.)">steptext currentstep</xsl:when>
               <xsl:otherwise>steptext</xsl:otherwise>
             </xsl:choose>
           </xsl:attribute>
           <a href="{f:href(/,.)}" onclick="_gaq.push(['_trackEvent', 'Tutorial', 'Bead: {f:href(/,.)}', 'click', 1]);"><xsl:apply-templates select="." mode="m:object-title-markup"/></a></span>
       </xsl:otherwise>
     </xsl:choose> 
    </div>
    </xsl:when>
      <xsl:otherwise>
        <xsl:message terminate="no">
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!          
WARNING: No more than six steps are allowed in a tutorial.
         Step number <xsl:value-of select="position()"/> truncated. 
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        </xsl:message>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>
  

  <xsl:function name="f:productname" as="xs:string">
    <xsl:param name="key"/>
    <xsl:choose>
      <xsl:when test="$key = 'servers'">Cloud Servers</xsl:when>
      <xsl:when test="$key= 'files'">Cloud Files</xsl:when>
      <xsl:when test="$key= 'clb'">Cloud Loadbalancers</xsl:when>
      <xsl:when test="$key= 'cm'">Cloud Montioring</xsl:when>
      <xsl:when test="$key= 'cdb'">Cloud Databases</xsl:when>
      <xsl:when test="$key= 'cbs'">Cloud Block Storage</xsl:when>
      <xsl:otherwise>&#160;</xsl:otherwise>
    </xsl:choose>
  </xsl:function>

  <xsl:function name="f:productnumber" as="xs:string">
    <xsl:param name="key"/>
    <xsl:choose>
      <xsl:when test="$key = 'servers'">1</xsl:when>
      <xsl:when test="$key= 'cdb'">2</xsl:when>
      <xsl:when test="$key= 'cm'">3</xsl:when>
      <xsl:when test="$key= 'cbs'">4</xsl:when>      
      <xsl:when test="$key= 'files'">5</xsl:when>
      <xsl:when test="$key= 'clb'">6</xsl:when>
      <xsl:when test="$key= 'auth'">7</xsl:when>
      <xsl:when test="$key= 'cdns'">8</xsl:when>      
      <xsl:otherwise>&#160;</xsl:otherwise>
    </xsl:choose>
  </xsl:function>
  
  <xsl:function name="f:calculatetype" as="xs:string">
    <xsl:param name="key"/>
    <xsl:choose>
      <xsl:when test="$key = 'concept'">1</xsl:when>
      <xsl:when test="$key= 'apiref'">2</xsl:when>
      <xsl:when test="$key= 'resource'">3</xsl:when>
      <xsl:when test="$key= 'tutorial'">4</xsl:when>      
      <xsl:when test="$key= 'apiref-mgmt'">5</xsl:when>
      <xsl:otherwise>100</xsl:otherwise>
    </xsl:choose>
  </xsl:function>
  
  <xsl:function name="f:calculatepriority">
    <xsl:param name="priority"/>
    <xsl:choose>
      <xsl:when test="normalize-space($priority) != ''">
        <xsl:value-of select="normalize-space($priority)"/>
      </xsl:when>
      <xsl:otherwise>100000</xsl:otherwise>
    </xsl:choose>
  </xsl:function>

  <xsl:function name="f:calculate-code-listing-tab-label" as="xs:string">
    <xsl:param name="example-title"/>
    <xsl:param name="section-title"/>
<!--    <xsl:message>#<xsl:value-of select="$example-title"/>$$
      <xsl:value-of select="$section-title"/>#</xsl:message>-->
    <xsl:choose>
      <xsl:when test="starts-with(normalize-space($example-title), normalize-space($section-title)) and contains($example-title,'Request')">Request</xsl:when>
      <xsl:when test="starts-with(normalize-space($example-title), normalize-space($section-title)) and contains($example-title,'Response')">Response</xsl:when>        
      <xsl:otherwise>
        <xsl:choose>
          <xsl:when test="ends-with(normalize-space($example-title),': JSON')">
            <xsl:value-of select="replace(normalize-space($example-title), '(.*): JSON$', '$1')"/>
          </xsl:when>
          <xsl:when test="ends-with(normalize-space($example-title),': XML')">
            <xsl:value-of select="replace(normalize-space($example-title), '(.*): XML$', '$1')"/>              
          </xsl:when>
          <xsl:otherwise>
            <!-- WTF? -->
            <xsl:value-of select="normalize-space($example-title)"/>              
          </xsl:otherwise>
        </xsl:choose>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:function>
  <xsl:function name="f:calculate-code-listing-tab-token" as="xs:string">
    <xsl:param name="example-title"/>
    <xsl:param name="section-title"/>
    <xsl:variable name="badchars">()"':;!@#$%^&amp;*= </xsl:variable>
    <xsl:value-of select="translate(normalize-space(f:calculate-code-listing-tab-label($example-title,$section-title)),$badchars,'_')"/>
  </xsl:function>

  <!-- This is from dist/xslt/base/html/verbatim.xsl and adds syntaxhighlighter to code listings. -->
  <xsl:param name="pygmenter-uri" select="''"/>
  <xsl:template match="db:programlisting|db:screen|db:synopsis
    |db:literallayout[@class='monospaced']"
    mode="programlisting-wadl">
    <xsl:param name="areas" select="()"/>
    <xsl:param name="first" />
    
    <xsl:variable name="pygments-pi" as="xs:string?"
      select="f:pi(/processing-instruction('dbhtml'), 'pygments')"/>
    
    <xsl:variable name="use-pygments" as="xs:boolean"
      select="$pygments-pi = 'true' or $pygments-pi = 'yes' or $pygments-pi = '1'
      or (contains(@role,'pygments') and not(contains(@role,'nopygments')))"/>
    
    <xsl:variable name="verbatim" as="node()*">
      <!-- n.b. look below where the class attribute is computed -->
      <xsl:choose>
        <xsl:when test="contains(@role,'nopygments') or string-length(.) &gt; 9000
          or self::db:literallayout or exists(*)">
          <xsl:apply-templates/>
        </xsl:when>
        <xsl:when test="$pygments-default = 0 and not($use-pygments)">
          <xsl:apply-templates/>
        </xsl:when>
        <xsl:when use-when="function-available('xdmp:http-post')"
          test="$pygmenter-uri != ''">
          <xsl:sequence select="ext:highlight(string(.), string(@language))"/>
        </xsl:when>
        <xsl:when use-when="function-available('ext:highlight')"
          test="true()">
          <xsl:sequence select="ext:highlight(string(.), string(@language))"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:apply-templates/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    
    <xsl:variable name="formatted" as="node()*">
      <xsl:call-template name="t:verbatim-patch-html">
        <xsl:with-param name="content" select="$verbatim"/>
        <xsl:with-param name="areas" select="$areas"/>
      </xsl:call-template>
    </xsl:variable>
    
    <xsl:variable name="lang" select="@language"/>
    
    <xsl:variable name="brush">
      <xsl:choose>
        <xsl:when test="@language = 'bash' or @language = 'BASH' or @language = 'sh'">bash</xsl:when>
        <xsl:when test="@language = 'javascript' or @language = 'JAVASCRIPT' or @language = 'js' or @language = 'JavaScript'">javascript</xsl:when>
        <xsl:when test="@language = 'xml' or @language = 'XML' or @language = 'atom'">xml</xsl:when>
        <xsl:when test="@language = 'java' or @language = 'JAVA'">java</xsl:when>
        <xsl:when test="@language = 'json' or @language = 'JSON'">json</xsl:when>
        <xsl:when test="@language = 'python' or @language = 'PYTHON' or @language = 'py' or @language = 'PY'">python</xsl:when>
        <xsl:otherwise>
          <xsl:message>
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
            WARNING: Unsupported langague on a <xsl:value-of select="local-name()"/>
            element: <xsl:value-of select="@language"/>
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
          </xsl:message>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    
    <xsl:variable name="syntaxhighlighter.switches">
      <xsl:choose>
        <xsl:when test="contains(@role,'gutter:') or contains(@role,'first-line:') or contains(@role,'highlight:')"><xsl:value-of select="@role"/></xsl:when>
      </xsl:choose>
    </xsl:variable>
      <!--
    <div>
      <xsl:sequence select="f:html-attributes(.)"/>-->
      <!--
      <xsl:variable name="tabToken" select="f:calculate-code-listing-tab-token((ancestor::db:example/db:info/db:title)[1], (ancestor::db:section/db:info/db:title)[1])"/>-->
      <xsl:variable name="tabToken" select="f:calculate-code-listing-tab-token((ancestor::db:example/db:info/db:title)[1], (ancestor::db:section[1]//db:title)[1])"/>
    <!-- Removed spaces before xsl:attribute so that if <pre> is schema validated
         and magically grows an xml:space="preserve" attribute, the processor
         doesn't fall over because we've added an attribute after a text node.
         Maybe this only happens in MarkLogic. Maybe it's a bug. For now: whatever. -->
      <div>
        <xsl:attribute name="class">
          <xsl:if test="not(normalize-space($tabToken) = '')"><xsl:value-of select="$tabToken"/> </xsl:if>
          <xsl:text> </xsl:text>
          <xsl:if test="$lang = 'xml'">raxXML</xsl:if>
          <xsl:if test="$lang = 'json' or $lang = 'javascript'">raxJSON</xsl:if>
          <xsl:if test="$lang = 'atom'">raxATOM</xsl:if>
        </xsl:attribute>
        <xsl:if test="$first">
          <xsl:attribute name="style">display: block;</xsl:attribute>
        </xsl:if>
      <pre><xsl:if test="not($lang = '')"><xsl:attribute name="class" select="concat('programlisting brush:',$brush, '; ', $syntaxhighlighter.switches)"/></xsl:if><!-- <xsl:if test="@language"><xsl:attribute name="class" select="@language"/></xsl:if> --><xsl:sequence select="$formatted"/></pre>
      </div>
<!--      <div class="Request raxJSON">
        <p>
          Request JSON not provided
        </p>
      </div>
      <div class="Response raxJSON">
        <p>
          Response JSON not provides.
        </p>
      </div>
      <div class="cURL raxXML">
        <p>
          cURL XML not provided
        </p>
      </div>
      <div class="Request raxXML">
        <p>
          Request XML not provided
        </p>
      </div>
      <div class="Response raxXML">
        <p>
          Response XML not provided
        </p>
      </div>      -->
  <!--    </div>-->

  </xsl:template>
  
  <xsl:param name="min-lines-for-boxed-codelisting">5</xsl:param>
  <xsl:template match="
    db:programlisting[count(tokenize(.,'&#xA;')) &gt; $min-lines-for-boxed-codelisting and not(parent::db:programlistingco)]|
    db:screen[count(tokenize(.,'&#xA;')) &gt; $min-lines-for-boxed-codelisting and not(parent::db:programlistingco)]|
    db:literallayout[@class='monospaced' and count(tokenize(.,'&#xA;')) &gt; $min-lines-for-boxed-codelisting and not(parent::db:programlistingco)]"
    mode="m:verbatim">
    <xsl:param name="areas" select="()"/>
    
    <xsl:variable name="pygments-pi" as="xs:string?"
      select="f:pi(/processing-instruction('dbhtml'), 'pygments')"/>
    
    <xsl:variable name="use-pygments" as="xs:boolean"
      select="$pygments-pi = 'true' or $pygments-pi = 'yes' or $pygments-pi = '1'
      or (contains(@role,'pygments') and not(contains(@role,'nopygments')))"/>
    
    <xsl:variable name="verbatim" as="node()*">
      <!-- n.b. look below where the class attribute is computed -->
      <xsl:choose>
        <xsl:when test="contains(@role,'nopygments') or string-length(.) &gt; 9000
          or self::db:literallayout or exists(*)">
          <xsl:apply-templates/>
        </xsl:when>
        <xsl:when test="$pygments-default = 0 and not($use-pygments)">
          <xsl:apply-templates/>
        </xsl:when>
        <xsl:when use-when="function-available('xdmp:http-post')"
          test="$pygmenter-uri != ''">
          <xsl:sequence select="ext:highlight(string(.), string(@language))"/>
        </xsl:when>
        <xsl:when use-when="function-available('ext:highlight')"
          test="true()">
          <xsl:sequence select="ext:highlight(string(.), string(@language))"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:apply-templates/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    
    <xsl:variable name="formatted" as="node()*">
      <xsl:call-template name="t:verbatim-patch-html">
        <xsl:with-param name="content" select="$verbatim"/>
        <xsl:with-param name="areas" select="$areas"/>
      </xsl:call-template>
    </xsl:variable>
    
    <xsl:variable name="lang" select="@language"/>
    
    <xsl:variable name="brush">
      <xsl:choose>
        <xsl:when test="@language = 'bash' or @language = 'BASH' or @language = 'sh'">bash</xsl:when>
        <xsl:when test="@language = 'javascript' or @language = 'JAVASCRIPT' or @language = 'js' or @language = 'JavaScript'">javascript</xsl:when>
        <xsl:when test="@language = 'xml' or @language = 'XML'">xml</xsl:when>
        <xsl:when test="@language = 'java' or @language = 'JAVA'">java</xsl:when>
        <xsl:when test="@language = 'json' or @language = 'JSON'">json</xsl:when>
        <xsl:when test="@language = 'python' or @language = 'PYTHON' or @language = 'py' or @language = 'PY'">python</xsl:when>
        <xsl:otherwise>
          <xsl:message>
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
            WARNING: Unsupported language on a <xsl:value-of select="local-name()"/>
            element: <xsl:value-of select="@language"/>
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
          </xsl:message>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    
    <xsl:variable name="syntaxhighlighter.switches">
      <xsl:choose>
        <xsl:when test="contains(@role,'gutter:') or contains(@role,'first-line:') or contains(@role,'highlight:')"><xsl:value-of select="@role"/></xsl:when>
      </xsl:choose>
    </xsl:variable>
    
    <div id="{generate-id()}" class="exampleblock">
<!--      <div class="exbuttons">
        <table class="typegroup">
          <tr>
            <td class="typebutton" onmousedown="ExMouseDown('cURL','{generate-id()}')" style="background-color:#DDD; font-weight:bold;color:#333">cURL</td>
            <td class="typebutton" onmousedown="ExMouseDown('Request', '{generate-id()}')">Request</td>
            <td class="typebutton" onmousedown="ExMouseDown('Response', '{generate-id()}')">Response</td>
          </tr>
        </table>
        <div class="formatgroup">
          <b>Format:</b> 
          <span 
            class="formatbutton" onmousedown="ExMouseDown('JSON', '{generate-id()}')" style="font-weight:bold">JSON</span>&#160;|&#160;<span 
              class="formatbutton" onmousedown="ExMouseDown('XML',  '{generate-id()}')">XML</span>
        </div>        
      </div>-->
      
      <div>
        <xsl:sequence select="f:html-attributes(.)"/>
        <xsl:attribute name="class">
          <xsl:value-of select="'excontent'"/> 
          <!-- n.b. look above where $verbatim is computed -->
          <xsl:choose>
            <xsl:when test="contains(@role,'nopygments') or string-length(.) &gt; 9000
              or self::db:literallayout or exists(*)"/>
            <xsl:when test="$pygments-default = 0 and not($use-pygments)"/>
            <xsl:when use-when="function-available('xdmp:http-post')"
              test="$pygmenter-uri != ''">
              <xsl:value-of select="' highlight'"/>
            </xsl:when>
            <xsl:when use-when="function-available('ext:highlight')"
              test="true()">
              <xsl:value-of select="' highlight'"/>
            </xsl:when>
            <xsl:otherwise/>
          </xsl:choose>
        </xsl:attribute>
        <!-- Removed spaces before xsl:attribute so that if <pre> is schema validated
         and magically grows an xml:space="preserve" attribute, the processor
         doesn't fall over because we've added an attribute after a text node.
         Maybe this only happens in MarkLogic. Maybe it's a bug. For now: whatever. -->
        <div class="cURL raxJSON Request raxXML Response">
          <pre><xsl:if test="not($lang = '')"><xsl:attribute name="class" select="concat('programlisting brush:',$brush, '; ', $syntaxhighlighter.switches)"/></xsl:if><!-- <xsl:if test="@language"><xsl:attribute name="class" select="@language"/></xsl:if> --><xsl:sequence select="$formatted"/></pre>
        </div>
      </div>
      <div class="copyexpand"> 
<!--        onmousedown="ExMouseDown('expand', '{generate-id()}')" -->
        <span class="excopybutton" onclick="highlightCode2(event);">select</span>&#160;|&#160;<span class="expandbutton" onmousedown="ExMouseDown('expand', '{generate-id()}',null,'action')">expand</span>
      </div>
    </div>
  </xsl:template>
  
  
  <xsl:template match="
    db:programlisting[parent::db:programlistingco]|
    db:screen[parent::db:programlistingco]|
    db:literallayout[@class='monospaced' and parent::db:programlistingco]"
    mode="m:verbatim">
    <xsl:param name="areas" select="()"/>
    
    <xsl:variable name="pygments-pi" as="xs:string?"
      select="f:pi(/processing-instruction('dbhtml'), 'pygments')"/>
    
    <xsl:variable name="use-pygments" as="xs:boolean"
      select="$pygments-pi = 'true' or $pygments-pi = 'yes' or $pygments-pi = '1'
      or (contains(@role,'pygments') and not(contains(@role,'nopygments')))"/>
    
    <xsl:variable name="verbatim" as="node()*">
      <!-- n.b. look below where the class attribute is computed -->
      <xsl:choose>
        <xsl:when test="contains(@role,'nopygments') or string-length(.) &gt; 9000
          or self::db:literallayout or exists(*)">
          <xsl:apply-templates/>
        </xsl:when>
        <xsl:when test="$pygments-default = 0 and not($use-pygments)">
          <xsl:apply-templates/>
        </xsl:when>
        <xsl:when use-when="function-available('xdmp:http-post')"
          test="$pygmenter-uri != ''">
          <xsl:sequence select="ext:highlight(string(.), string(@language))"/>
        </xsl:when>
        <xsl:when use-when="function-available('ext:highlight')"
          test="true()">
          <xsl:sequence select="ext:highlight(string(.), string(@language))"/>
        </xsl:when>
        <xsl:otherwise>
          <xsl:apply-templates/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    
    <xsl:variable name="formatted" as="node()*">
      <xsl:call-template name="t:verbatim-patch-html">
        <xsl:with-param name="content" select="$verbatim"/>
        <xsl:with-param name="areas" select="$areas"/>
      </xsl:call-template>
    </xsl:variable>
    
    <xsl:variable name="lang" select="@language"/>
    
    <xsl:variable name="brush">
      <xsl:choose>
        <xsl:when test="@language = 'bash' or @language = 'BASH' or @language = 'sh'">bash</xsl:when>
        <xsl:when test="@language = 'javascript' or @language = 'JAVASCRIPT' or @language = 'js' or @language = 'JavaScript'">javascript</xsl:when>
        <xsl:when test="@language = 'xml' or @language = 'XML'">xml</xsl:when>
        <xsl:when test="@language = 'java' or @language = 'JAVA'">java</xsl:when>
        <xsl:when test="@language = 'json' or @language = 'JSON'">json</xsl:when>
        <xsl:when test="@language = 'python' or @language = 'PYTHON' or @language = 'py' or @language = 'PY'">python</xsl:when>
        <xsl:otherwise>
          <xsl:message>
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
            WARNING: Unsupported language on a <xsl:value-of select="local-name()"/>
            element: <xsl:value-of select="@language"/>
            %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
          </xsl:message>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    
    <xsl:variable name="syntaxhighlighter.switches">
      <xsl:choose>
        <xsl:when test="contains(@role,'gutter:') or contains(@role,'first-line:') or contains(@role,'highlight:')"><xsl:value-of select="@role"/></xsl:when>
      </xsl:choose>
    </xsl:variable>
      
      <div>
        <xsl:sequence select="f:html-attributes(.)"/>
        <xsl:attribute name="class">
          <!-- n.b. look above where $verbatim is computed -->
          <xsl:choose>
            <xsl:when test="contains(@role,'nopygments') or string-length(.) &gt; 9000
              or self::db:literallayout or exists(*)"/>
            <xsl:when test="$pygments-default = 0 and not($use-pygments)"/>
            <xsl:when use-when="function-available('xdmp:http-post')"
              test="$pygmenter-uri != ''">
              <xsl:value-of select="' highlight'"/>
            </xsl:when>
            <xsl:when use-when="function-available('ext:highlight')"
              test="true()">
              <xsl:value-of select="' highlight'"/>
            </xsl:when>
            <xsl:otherwise/>
          </xsl:choose>
        </xsl:attribute>
        <!-- Removed spaces before xsl:attribute so that if <pre> is schema validated
         and magically grows an xml:space="preserve" attribute, the processor
         doesn't fall over because we've added an attribute after a text node.
         Maybe this only happens in MarkLogic. Maybe it's a bug. For now: whatever. -->
          <pre><xsl:if test="not($lang = '')"><xsl:attribute name="class" select="concat('programlisting brush:',$brush, '; ', $syntaxhighlighter.switches)"/></xsl:if><!-- <xsl:if test="@language"><xsl:attribute name="class" select="@language"/></xsl:if> --><xsl:sequence select="$formatted"/></pre>
      </div>
  </xsl:template>
  
  <xsl:template match="db:example[@role = 'wadl']">
    <xsl:variable name="id" select="generate-id()"/>
    <xsl:variable name="exampleTypeDefault" select="f:calculate-code-listing-tab-token((db:info/db:title)[1], (ancestor::db:section[1]//db:title)[1])"/>
    <xsl:choose>
      <xsl:when test="following-sibling::db:example[@role = 'wadl'] and not(preceding-sibling::db:example[@role = 'wadl']) ">        
        <div id="{$id}" class="exampleblock">
          <div class="exbuttons">
            <table class="typegroup">
              <tr>
                <!-- TODO: Only put the things here you need -->    
                <xsl:variable name="tabs">
                 <xsl:apply-templates select="db:programlisting" mode="programlisting-req-resp-buttons">
                    <xsl:with-param name="id" select="$id"/>
                    <xsl:with-param name="exampleTypeDefault" select="$exampleTypeDefault"/>
                    <xsl:with-param name="defaultTab" select="1"/>
                 </xsl:apply-templates>
                  <xsl:apply-templates select="following-sibling::db:example[@role = 'wadl']/db:programlisting" mode="programlisting-req-resp-buttons">
                    <xsl:with-param name="id" select="$id"/>
                    <xsl:with-param name="exampleTypeDefault" select="$exampleTypeDefault"/>
                  </xsl:apply-templates>
                </xsl:variable>
                <xsl:for-each-group select="$tabs/*" group-by="@onmousedown">
                  <xsl:copy-of select="current-group()[1]"/>
                </xsl:for-each-group>
                <!--
                <td class="typebutton" onmousedown="ExMouseDown('cURL','{generate-id()}')" style="background-color:#DDD; font-weight:bold;color:#333">cURL</td>
                <td class="typebutton" onmousedown="ExMouseDown('Request', '{generate-id()}')">Request</td>
                <td class="typebutton" onmousedown="ExMouseDown('Response', '{generate-id()}')">Response</td>
                -->
              </tr>
            </table>
            <xsl:if test="../db:example[@role = 'wadl']/db:programlisting[@language = 'xml'] and 
                         (../db:example[@role = 'wadl']/db:programlisting[@language = 'javascript'] or 
                          ../db:example[@role = 'wadl']/db:programlisting[@language = 'json'])" >
              <div class="formatgroup"> 
                <b>Format:&#160;</b> 
                <span 
                  class="formatbutton" onmousedown="ExMouseDown('raxJSON', '{$id}','{$exampleTypeDefault}', 'format')" style="font-weight:bold">JSON</span>&#160;|&#160;<span 
                    class="formatbutton" onmousedown="ExMouseDown('raxXML',  '{$id}','{$exampleTypeDefault}', 'format')">XML</span>
              </div>
            </xsl:if>        
          </div>
          <div class="excontent">
            <!-- programlisting divs here: TODO: Wrap each in a diff with class="Request raxXML" or whatever -->          
            <xsl:apply-templates select="db:programlisting" mode="programlisting-wadl">
              <xsl:with-param name="first" select="true()"/>
            </xsl:apply-templates>
            <xsl:apply-templates select="following-sibling::db:example[@role = 'wadl']/db:programlisting" mode="programlisting-wadl"/>
          </div>
          <div class="copyexpand">
            <span class="excopybutton" onclick="highlightCode2(event);">select</span>&#160;|&#160;<span class="expandbutton" onmousedown="ExMouseDown('expand', '{generate-id()}',null,'action')">expand</span>
          </div>
        </div>
      </xsl:when>
      <xsl:when test="preceding-sibling::db:example[@role = 'wadl']">
        <!-- Nuke it: we did a paneled code block -->   
      </xsl:when>      
      <xsl:otherwise>
        <!-- Weird situation, process with db templates -->
        <xsl:apply-imports/>  
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template match="db:programlisting" mode="programlisting-req-resp-buttons">
    <xsl:param name="id"/>
    <xsl:param name="exampleTypeDefault"/>
    <xsl:param name="defaultTab" select="0"/>
    <xsl:variable name="tabLabel" select="f:calculate-code-listing-tab-label((ancestor::db:example/db:info/db:title)[1], (ancestor::db:section[1]//db:title)[1])"/>
    <xsl:variable name="tabToken" select="f:calculate-code-listing-tab-token((ancestor::db:example/db:info/db:title)[1], (ancestor::db:section[1]//db:title)[1])"/>

    <!--<xsl:variable name="badchars">()"':;!@#$%^&amp;*=</xsl:variable>-->
    <!-- TODO: figure out which to make the default: style="background-color:#DDD; font-weight:bold;color:#333" -->
    <!-- <td class="typebutton" onmousedown="ExMouseDown('{translate($tabName,$badchars,'_')}','{$id}')"><xsl:value-of select="$tabName"/></td>-->
    <td class="typebutton" onmousedown="ExMouseDown('{$tabToken}','{$id}','{$exampleTypeDefault}', 'tab')"><xsl:if test="$defaultTab = 1">
        <xsl:attribute name="style">background-color:#DDD; font-weight:bold;color:#333</xsl:attribute>
      </xsl:if><xsl:value-of select="$tabLabel"/></td>
  </xsl:template>

<!-- HACK ALERT: TECHNICAL DEBT!!! We're removing the link to the callout 
  to make this work with the syntaxhighlighting. -->
  <xsl:template match="ghost:co" mode="mp:expand-ghost-co">
    <xsl:if test="@xml:id">
      <!-- DWC: HACK -->
      <!-- <a name="{@xml:id}"/> -->
    </xsl:if>
    <xsl:call-template name="t:callout-bug">
      <xsl:with-param name="conum">
        <xsl:choose>
          <xsl:when test="@number">
            <xsl:value-of select="@number"/>
          </xsl:when>
          <xsl:otherwise>
            <xsl:number count="ghost:co"
              level="any"
              from="db:programlisting|db:screen|db:literallayout|db:synopsis"
              format="1"/>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:with-param>
    </xsl:call-template>
  </xsl:template>


  <xsl:template name="t:head">
    <xsl:param name="node" select="."/>
    <xsl:param name="prodname" />
    <head>
      <title>
        <xsl:value-of select="f:title($node)"/><xsl:text> - </xsl:text><xsl:value-of select="$prodname"/>
      </title>

      <xsl:if test="$html.base != ''">
        <base href="{$html.base}"/>
      </xsl:if>

      <xsl:call-template name="t:system-head-content">
        <xsl:with-param name="node" select="$node"/>
      </xsl:call-template>

      <xsl:call-template name="t:head-meta">
        <xsl:with-param name="node" select="$node"/>
      </xsl:call-template>

      <xsl:call-template name="t:head-links">
        <xsl:with-param name="node" select="$node"/>
      </xsl:call-template>

      <xsl:if test="($draft.mode = 'yes'
                     or ($draft.mode = 'maybe' and
		         $node/ancestor-or-self::*[@status][1]/@status = 'draft'))
                    and $draft.watermark.image != ''">
        <style type="text/css">
          body { background-image: url('<xsl:value-of select="$draft.watermark.image"/>');
            background-repeat: no-repeat;
            background-position: center center;
            /* The following property make the watermark "fixed" on the page. */
            /* I think that's just a bit too distracting for the reader... */
            /* background-attachment: fixed; */
          }
        </style>
      </xsl:if>

      <xsl:if test="$html.stylesheets != ''">
        <xsl:for-each select="tokenize($html.stylesheets, '\s+')">
          <link rel="stylesheet" href="{.}">
            <xsl:choose>
              <xsl:when test="ends-with(.,'.css')">
                <xsl:attribute name="type" select="'text/css'"/>
              </xsl:when>
              <xsl:otherwise>
                <!-- ??? what type is this ??? -->
              </xsl:otherwise>
            </xsl:choose>
          </link>
        </xsl:for-each>
      </xsl:if>

      <xsl:call-template name="t:javascript">
        <xsl:with-param name="node" select="$node"/>
      </xsl:call-template>

      <xsl:call-template name="t:user-head-content">
        <xsl:with-param name="node" select="$node"/>
      </xsl:call-template>
    </head>
  </xsl:template>
  
</xsl:stylesheet>
