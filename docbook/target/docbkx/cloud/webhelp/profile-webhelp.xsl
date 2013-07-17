<?xml version="1.1" encoding="UTF-8"?>
<xsl:stylesheet 
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" 
    xmlns:exslt="http://exslt.org/common" 
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:d="http://docbook.org/ns/docbook"
    xmlns:wadl="http://wadl.dev.java.net/2009/02" 
    xmlns:rax="http://docs.rackspace.com/api" 
    xmlns="http://www.w3.org/1999/xhtml" 
    version="1.0" 
    exclude-result-prefixes="exslt d wadl rax xlink">

  <!-- First import the non-chunking templates that format elements
       within each chunk file. In a customization, you should
       create a separate non-chunking customization layer such
       as mydocbook.xsl that imports the original docbook.xsl and
       customizes any presentation templates. Then your chunking
       customization should import mydocbook.xsl instead of
       docbook.xsl.  -->
  <xsl:import href="docbook.xsl"/>

  <!-- chunk-common.xsl contains all the named templates for chunking.
       In a customization file, you import chunk-common.xsl, then
       add any customized chunking templates of the same name. 
       They will have import precedence over the original 
       chunking templates in chunk-common.xsl. -->
  <xsl:import href="webhelp-chunk-common.xsl"/>

  <!-- The manifest.xsl module is no longer imported because its
       templates were moved into chunk-common and chunk-code -->

  <!-- chunk-code.xsl contains all the chunking templates that use
       a match attribute.  In a customization it should be referenced
       using <xsl:include> instead of <xsl:import>, and then add
       any customized chunking templates with match attributes. But be sure
       to add a priority="1" to such customized templates to resolve
       its conflict with the original, since they have the
       same import precedence.
       
       Using xsl:include prevents adding another layer
       of import precedence, which would cause any
       customizations that use xsl:apply-imports to wrongly
       apply the chunking version instead of the original
       non-chunking version to format an element.  -->
  <xsl:include href="urn:docbkx:stylesheet-base/xhtml/profile-chunk-code.xsl" />


  <xsl:param name="builtForOpenStack">0</xsl:param>
  <!-- ======================================== -->

  <xsl:variable name="preprocessed-nodes">
    <xsl:apply-templates select="exslt:node-set($profiled-nodes)" mode="preprocess"/>
  </xsl:variable>

  <xsl:template match="@*|node()" mode="preprocess">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()" mode="preprocess"/>
    </xsl:copy>
  </xsl:template>

  <xsl:template match="d:legalnotice" mode="preprocess">
    <xsl:message>
########################################
Processing legalnotice: <xsl:value-of select="@role"/>
########################################
    </xsl:message>
    <d:legalnotice>
      <xsl:apply-templates select="@*" mode="preprocess"/>
      <xsl:choose>
	<xsl:when test="starts-with(string(@role),'cc-')">
	  <xsl:call-template name="CCLegalNotice" />
	</xsl:when>
	<xsl:when test="@role = 'rs-api'">
	  <xsl:call-template name="RSAPILegalNotice"/>
	</xsl:when>
	<xsl:when test="@role = 'apache2'">
	  <xsl:call-template name="Apache2LegalNotice"/>
	</xsl:when>
      </xsl:choose>
      
      <xsl:if test="$builtForOpenStack != 0 and not(preceding-sibling::d:legalnotice)">
        <d:link xlink:href="http://www.openstack.org">
          <d:informalfigure>
            <d:mediaobject>
              <d:imageobject>
                <d:imagedata fileref="{$webhelp.common.dir}images/built-for-openstack.png"/>
              </d:imageobject>
            </d:mediaobject>
          </d:informalfigure>
        </d:link>
      </xsl:if>
      
    </d:legalnotice>	  

  </xsl:template>

  <!--
      The abstract is supressed if the rs-api legal notice is used, as
      it's incorporated into the document in this case.
  -->
  <xsl:template match="d:abstract" mode="preprocess">
    <xsl:choose>
      <xsl:when test="/*//d:legalnotice[@role = 'rs-api']" />
      <xsl:otherwise>
	<xsl:copy>
	  <xsl:apply-templates select="@*|node()" mode="preprocess"/>
	</xsl:copy>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>
  
  <xsl:template name="Apache2LegalNotice">
      <xsl:variable name="a2Link" select="'http://www.apache.org/licenses/LICENSE-2.0'"/>
      <xsl:if test="@role = 'apache2'">
          <d:para>
              Licensed under the Apache License, Version 2.0 (the "License");
              you may not use this file except in compliance with the License.
              You may obtain a copy of the License at
	  </d:para>
	  <d:para>
	    <xsl:element name="d:link">
	      <xsl:attribute name="xlink:href">
		<xsl:value-of select="$a2Link"/>
	      </xsl:attribute>
	      <xsl:value-of select="$a2Link"/>
	    </xsl:element>
	  </d:para>
	  <d:para>
              Unless required by applicable law or agreed to in writing, software
              distributed under the License is distributed on an "AS IS" BASIS,
              WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
              See the License for the specific language governing permissions and
              limitations under the License.
	  </d:para>
      </xsl:if>
  </xsl:template>

  <xsl:template name="RSAPILegalNotice">
      <xsl:if test="@role = 'rs-api'">
          <d:para>
              <xsl:value-of select="/*/d:info/d:abstract"/>
              The document is for informational purposes only and is
              provided “AS IS.”
          </d:para>
          <d:para>
              RACKSPACE MAKES NO REPRESENTATIONS OR WARRANTIES OF ANY
              KIND, EXPRESS OR IMPLIED, AS TO THE ACCURACY OR
              COMPLETENESS OF THE CONTENTS OF THIS DOCUMENT AND
              RESERVES THE RIGHT TO MAKE CHANGES TO SPECIFICATIONS AND
              PRODUCT/SERVICES DESCRIPTION AT ANY TIME WITHOUT NOTICE.
              RACKSPACE SERVICES OFFERINGS ARE SUBJECT TO CHANGE
              WITHOUT NOTICE.  USERS MUST TAKE FULL RESPONSIBILITY FOR
              APPLICATION OF ANY SERVICES MENTIONED HEREIN.  EXCEPT AS
              SET FORTH IN RACKSPACE GENERAL TERMS AND CONDITIONS
              AND/OR CLOUD TERMS OF SERVICE, RACKSPACE ASSUMES NO
              LIABILITY WHATSOEVER, AND DISCLAIMS ANY EXPRESS OR
              IMPLIED WARRANTY, RELATING TO ITS SERVICES INCLUDING,
              BUT NOT LIMITED TO, THE IMPLIED WARRANTY OF
              MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
              NONINFRINGEMENT.
          </d:para>
          <d:para>
              Except as expressly provided in any written license
              agreement from Rackspace, the furnishing of this
              document does not give you any license to patents,
              trademarks, copyrights, or other intellectual property.
          </d:para>
          <d:para>
              Rackspace®, Rackspace logo and Fanatical Support® are
              registered service marks of Rackspace US,
              Inc. All other product names and trademarks
              used in this document are for identification purposes
              only and are property of their respective owners.
          </d:para>
      </xsl:if>
  </xsl:template>

  <xsl:template name="CCLegalNotice">
      <xsl:if test="starts-with(string(@role),'cc-')">
          <xsl:variable name="ccid"><xsl:value-of select="substring-after(string(@role),'cc-')"/></xsl:variable>
	  <xsl:variable name="ccidURL">http://creativecommons.org/licenses/<xsl:value-of select="$ccid"/>/3.0/legalcode</xsl:variable>

        <d:informaltable frame="void">
            <d:col width="10%"/>
            <d:col width="90%"/>
            <d:tbody>
                <d:tr>
		  <d:td>
		    <d:link xlink:href="{$ccidURL}">
		      <d:informalfigure>
			<d:mediaobject>
			  <d:imageobject>
			    <d:imagedata
				fileref="{$webhelp.common.dir}images/cc/{$ccid}.png"
				align="center" 
				valign="middle"/>
			  </d:imageobject>
			</d:mediaobject>
		      </d:informalfigure>
		    </d:link>
		  </d:td>
		  <d:td>
		    <d:para>Except where otherwise noted, this document is licensed under 
		    <xsl:element name="d:link">
		      <xsl:attribute name="xlink:href">
			<xsl:value-of select="$ccidURL"/>
		      </xsl:attribute>
		      <d:emphasis role="bold">
			Creative Commons Attribution
			<xsl:choose>
			  <xsl:when test="$ccid = 'by'" />
			  <xsl:when test="$ccid = 'by-sa'">
			    <xsl:text>ShareAlike</xsl:text>
			  </xsl:when>
			  <xsl:when test="$ccid = 'by-nd'">
			    <xsl:text>NoDerivatives</xsl:text>
			  </xsl:when>
			  <xsl:when test="$ccid = 'by-nc'">
			    <xsl:text>NonCommercial</xsl:text>
			  </xsl:when>
			  <xsl:when test="$ccid = 'by-nc-sa'">
			    <xsl:text>NonCommercial ShareAlike</xsl:text>
			  </xsl:when>
			  <xsl:when test="$ccid = 'by-nc-nd'">
			    <xsl:text>NonCommercial NoDerivatives</xsl:text>
			  </xsl:when>
			  <xsl:otherwise>
			    <xsl:message terminate="yes">
			      I don't understand licence <xsl:value-of select="$ccid"/>
			    </xsl:message>
			  </xsl:otherwise>
			</xsl:choose>
			3.0 License
		      </d:emphasis>				   
		    </xsl:element>
		    </d:para>
		    <d:para>
		      <d:link xlink:href="{$ccidURL}">
			<xsl:value-of select="$ccidURL"/>
		      </d:link>
		    </d:para>
		  </d:td>
		</d:tr>
            </d:tbody>
	</d:informaltable>
      </xsl:if>
  </xsl:template>


<xsl:template match="/" priority="1">
  <!-- * Get a title for current doc so that we let the user -->
  <!-- * know what document we are processing at this point. -->
  <xsl:variable name="doc.title">
    <xsl:call-template name="get.doc.title"/>
  </xsl:variable>
  
  <xsl:choose>   
    <xsl:when test="false()"/>
    <!-- Can't process unless namespace removed -->
    <xsl:when test="false()"/>
    <xsl:otherwise>
      <xsl:choose>
        <xsl:when test="$rootid != ''">
          <xsl:choose>
            <xsl:when test="count($preprocessed-nodes//*[@id=$rootid]) = 0">
              <xsl:message terminate="yes">
                <xsl:text>ID '</xsl:text>
                <xsl:value-of select="$rootid"/>
                <xsl:text>' not found in document.</xsl:text>
              </xsl:message>
            </xsl:when>
            <xsl:otherwise>
              <xsl:if test="$collect.xref.targets = 'yes' or                             $collect.xref.targets = 'only'">
                <xsl:apply-templates select="key('id', $rootid)" mode="collect.targets"/>
              </xsl:if>
              <xsl:if test="$collect.xref.targets != 'only'">
                <xsl:apply-templates select="exslt:node-set($preprocessed-nodes//*[@id=$rootid])" mode="process.root"/>
                <xsl:if test="$tex.math.in.alt != ''">
                  <xsl:apply-templates select="exslt:node-set($preprocessed-nodes//*[@id=$rootid])" mode="collect.tex.math"/>
                </xsl:if>
                <xsl:if test="$generate.manifest != 0">
                  <xsl:call-template name="generate.manifest">
                    <xsl:with-param name="node" select="key('id',$rootid)"/>
                  </xsl:call-template>
                </xsl:if>
              </xsl:if>
            </xsl:otherwise>
          </xsl:choose>
        </xsl:when>
        <xsl:otherwise>
          <xsl:if test="$collect.xref.targets = 'yes' or                         $collect.xref.targets = 'only'">
            <xsl:apply-templates select="exslt:node-set($preprocessed-nodes)" mode="collect.targets"/>
          </xsl:if>
          <xsl:if test="$collect.xref.targets != 'only'">
            <xsl:apply-templates select="exslt:node-set($preprocessed-nodes)" mode="process.root"/>
            <xsl:if test="$tex.math.in.alt != ''">
              <xsl:apply-templates select="exslt:node-set($preprocessed-nodes)" mode="collect.tex.math"/>
            </xsl:if>
            <xsl:if test="$generate.manifest != 0">
              <xsl:call-template name="generate.manifest">
                <xsl:with-param name="node" select="exslt:node-set($preprocessed-nodes)"/>
              </xsl:call-template>
            </xsl:if>
          </xsl:if>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:otherwise>
  </xsl:choose>
  
  <xsl:call-template name="index.html"/>
  <xsl:call-template name="revhistory2atom"/>

</xsl:template>

<xsl:template match="d:releaseinfo" mode="rackspace-title">
  &#160;-&#160;<xsl:value-of select="normalize-space(.)"/>
</xsl:template>


    <!-- 
	 DWC: Overriding this template from xhtml/profile-docbook.xsl
	      to control what appears in head/title
    -->
<xsl:template name="head.content">
  <xsl:param name="node" select="."/>
  <xsl:param name="title">
    <xsl:apply-templates select="$node" mode="object.title.markup.textonly"/>
  </xsl:param>

  <title><!-- DWC: Adding stuff to title for SEO -->
    <xsl:copy-of select="$title"/>&#160;-&#160;<xsl:value-of select="//d:title[1]"/><xsl:apply-templates select="/*/d:info/d:releaseinfo[1]" mode="rackspace-title"/>
  </title>

  <xsl:if test="$html.base != ''">
    <base href="{$html.base}"/>
  </xsl:if>

  <!-- Insert links to CSS files or insert literal style elements -->
  <xsl:call-template name="generate.css"/>

  <xsl:if test="$html.stylesheet != ''">
    <xsl:call-template name="output.html.stylesheets">
      <xsl:with-param name="stylesheets" select="normalize-space($html.stylesheet)"/>
    </xsl:call-template>
  </xsl:if>

  <xsl:if test="$link.mailto.url != ''">
    <link rev="made" href="{$link.mailto.url}"/>
  </xsl:if>

  <meta name="generator" content="DocBook {$DistroTitle} V{$VERSION}"/>
  <meta name="mavenGroupId" content="{$groupId}"/>
  <meta name="mavenArtifactId" content="{$artifactId}"/>
  <meta name="mavenVersionId" content="{$docProjectVersion}"/>
  
  <xsl:if test="$generate.meta.abstract != 0">
    <xsl:variable name="info" select="(d:articleinfo                                       |d:bookinfo                                       |d:prefaceinfo                                       |d:chapterinfo                                       |d:appendixinfo                                       |d:sectioninfo                                       |d:sect1info                                       |d:sect2info                                       |d:sect3info                                       |d:sect4info                                       |d:sect5info                                       |d:referenceinfo                                       |d:refentryinfo                                       |d:partinfo                                       |d:info                                       |d:docinfo)[1]"/>
    <xsl:if test="$info and $info/d:abstract">
      <meta name="description">
        <xsl:attribute name="content">
          <xsl:for-each select="$info/d:abstract[1]/*">
            <xsl:value-of select="normalize-space(.)"/>
            <xsl:if test="position() &lt; last()">
              <xsl:text> </xsl:text>
            </xsl:if>
          </xsl:for-each>
        </xsl:attribute>
      </meta>
    </xsl:if>
  </xsl:if>

  <xsl:if test="($draft.mode = 'yes' or                 ($draft.mode = 'maybe' and                 ancestor-or-self::*[@status][1]/@status = 'draft'))                 and $draft.watermark.image != ''">
    <style type="text/css"><xsl:text>
body { background-image: url('</xsl:text>
<xsl:value-of select="$draft.watermark.image"/><xsl:text>');
       background-repeat: no-repeat;
       background-position: top left;
       /* The following properties make the watermark "fixed" on the page. */
       /* I think that's just a bit too distracting for the reader... */
       /* background-attachment: fixed; */
       /* background-position: center center; */
     }</xsl:text>
    </style>
  </xsl:if>
  <xsl:apply-templates select="." mode="head.keywords.content"/>
</xsl:template>

</xsl:stylesheet>